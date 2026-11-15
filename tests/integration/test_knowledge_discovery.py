import pytest
from unittest.mock import patch
from src.domains.project.facade.project import ProjectFacade
from src.domains.project.models.contract.project import ProjectCreateContract
from src.domains.discovery.facade.discovery import DiscoveryFacade
from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
from src.services.graph.memgraph_client import MemgraphClient


@pytest.mark.asyncio
async def test_knowledge_discovery_ingestion_and_phase1():
    project_facade = ProjectFacade()
    discovery_facade = DiscoveryFacade()
    project_id = "test-proj-kdg-us1"

    # 1. Cleanup
    try:
        await project_facade.delete_project(project_id)
    except Exception:
        pass

    # 2. Create Project with alice as owner
    await project_facade.create_project(
        ProjectCreateContract(
            project_id=project_id,
            name="KDG Test Project",
            description="Testing Phase 1 & 2 knowledge discovery",
        ),
        creator_user_id="alice",
    )

    # 3. Ingest Tabular CSV data
    csv_bytes = b"subject_id,blood_pressure,contact_email\n123e4567-e89b-12d3-a456-426614174000,120,alice@hospital.org\n550e8400-e29b-41d4-a716-446655440000,135,bob@hospital.org\n"
    res = await project_facade.ingest_tabular(
        project_id=project_id,
        dataset_name="patient_records",
        data_bytes=csv_bytes,
        filename="patients.csv",
        tier="BRONZE",
    )
    assert res.status == "SUCCESS"
    assert res.records_ingested == 2

    # 4. Assert Phase 1 summary immediately present via DiscoveryFacade
    user_context = {"sub": "alice", "roles": ["user"]}
    knowledge = await discovery_facade.get_workspace_knowledge(project_id, user=user_context)
    assert knowledge is not None
    assert knowledge.project_id == project_id
    assert len(knowledge.resources) >= 1

    resource = next((r for r in knowledge.resources if r.resource_id == "patient_records"), None)
    assert resource is not None
    assert resource.record_count == 2
    assert resource.format == "CSV"

    attr_names = [a.name for a in resource.attributes]
    assert "subject_id" in attr_names
    assert "contact_email" in attr_names

    # 5. Non-member access returns None (confined)
    stranger_context = {"sub": "stranger", "roles": ["user"]}
    non_member_res = await discovery_facade.get_workspace_knowledge(project_id, user=stranger_context)
    assert non_member_res is None

    # 6. Verify ingestion does not fail if indexing raises an unexpected exception (FR-019)
    with patch("src.domains.discovery.operations.structural_indexer.StructuralIndexer.index_resource", side_effect=RuntimeError("Index crash")):
        ingest_res = await project_facade.ingest_tabular(
            project_id=project_id,
            dataset_name="metrics_resilient",
            data_bytes=b"a,b\n1,2\n",
            filename="metrics.csv",
            tier="BRONZE",
        )
        assert ingest_res.status == "SUCCESS"
        assert ingest_res.records_ingested == 1

    # 7. Cleanup
    await project_facade.delete_project(project_id)


@pytest.mark.asyncio
async def test_cross_project_correlation_and_member_scoping():
    project_facade = ProjectFacade()
    discovery_facade = DiscoveryFacade()
    from src.domains.project.operations.membership import ProjectMembershipService
    membership_service = ProjectMembershipService()

    proj_a = "test-proj-scope-a"
    proj_b = "test-proj-scope-b"

    # Cleanup
    for p in (proj_a, proj_b):
        try:
            await project_facade.delete_project(p)
        except Exception:
            pass

    # Create Proj A (owner: alice) and Proj B (owner: bob)
    await project_facade.create_project(
        ProjectCreateContract(project_id=proj_a, name="Project Alpha"),
        creator_user_id="alice",
    )
    await project_facade.create_project(
        ProjectCreateContract(project_id=proj_b, name="Project Beta"),
        creator_user_id="bob",
    )

    # Ingest shared entity value into Proj A
    csv_a = b"account_num,balance\nACCT-99812,500.0\n"
    await project_facade.ingest_tabular(
        project_id=proj_a,
        dataset_name="accounts_a",
        data_bytes=csv_a,
        filename="accounts.csv",
        tier="BRONZE",
    )

    # Ingest shared entity value into Proj B
    csv_b = b"customer_id,debt\nACCT-99812,1200.0\n"
    await project_facade.ingest_tabular(
        project_id=proj_b,
        dataset_name="accounts_b",
        data_bytes=csv_b,
        filename="accounts.csv",
        tier="BRONZE",
    )

    alice_ctx = {"sub": "alice", "roles": ["user"]}

    # 1. Alice is only member of Proj A: sees only Proj A, zero trace of Proj B
    res_single = await discovery_facade.find_entities(value="ACCT-99812", user=alice_ctx)
    assert res_single.total_projects == 1
    assert len(res_single.matches) == 1
    assert res_single.matches[0].project_id == proj_a
    # Confirm no location_uri or S3 path leaked in EntityMatch model
    match_dict = res_single.matches[0].model_dump()
    assert "location_uri" not in match_dict
    assert "storage_uri" not in match_dict

    # 2. Add Alice as member of Proj B
    membership_service.add_member(proj_b, user_id="alice", role="member", added_by="bob")

    # Evaluated immediately without caching
    res_both = await discovery_facade.find_entities(value="ACCT-99812", user=alice_ctx)
    assert res_both.total_projects == 2
    assert len(res_both.matches) == 2
    matched_projects = {m.project_id for m in res_both.matches}
    assert matched_projects == {proj_a, proj_b}

    # 3. Remove Alice from Proj B
    membership_service.remove_member(proj_b, user_id="alice")

    # Evaluated immediately on next request: back to only Proj A
    res_after_removal = await discovery_facade.find_entities(value="ACCT-99812", user=alice_ctx)
    assert res_after_removal.total_projects == 1
    assert res_after_removal.matches[0].project_id == proj_a

    # Cleanup
    for p in (proj_a, proj_b):
        await project_facade.delete_project(p)


@pytest.mark.asyncio
async def test_pipeline_run_emits_lineage_and_derived_from():
    project_facade = ProjectFacade()
    discovery_facade = DiscoveryFacade()
    from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
    kdg_store = KDGGraphStore()

    project_id = "test-proj-lineage-pipe"

    # Cleanup
    try:
        await project_facade.delete_project(project_id)
    except Exception:
        pass

    # Create project
    await project_facade.create_project(
        ProjectCreateContract(project_id=project_id, name="Lineage Test Project"),
        creator_user_id="alice",
    )

    # Ingest bronze dataset
    csv_bytes = b"event_id,val\n1,100\n2,200\n"
    await project_facade.ingest_tabular(
        project_id=project_id,
        dataset_name="bronze_events",
        data_bytes=csv_bytes,
        filename="events.csv",
        tier="BRONZE",
    )

    # Ingest gold dataset
    gold_bytes = b"kpi,val\navg,150\n"
    await project_facade.ingest_tabular(
        project_id=project_id,
        dataset_name="gold_kpi",
        data_bytes=gold_bytes,
        filename="kpi.csv",
        tier="GOLD",
    )

    # Record pipeline execution connecting bronze_events -> gold_kpi
    kdg_store.record_pipeline_execution(
        run_id="run-pipe-101",
        pipeline_id="pipe-kpi-agg",
        project_id=project_id,
        status="SUCCESS",
        input_datasets=["bronze_events"],
        target_dataset="gold_kpi",
    )

    alice_ctx = {"sub": "alice", "roles": ["user"]}

    # Retrieve lineage for gold_kpi
    lineage = await discovery_facade.get_lineage(
        project_id=project_id,
        dataset_id="gold_kpi",
        user=alice_ctx,
    )

    assert lineage.is_root is False
    assert len(lineage.edges) >= 1
    edge = next((e for e in lineage.edges if e.source == "bronze_events" and e.target == "gold_kpi"), None)
    assert edge is not None
    assert edge.relationship == "DERIVED_FROM"

    node_ids = {n.resource_id for n in lineage.nodes}
    assert "bronze_events" in node_ids
    assert "gold_kpi" in node_ids

    # Cleanup
    await project_facade.delete_project(project_id)


@pytest.mark.asyncio
async def test_natural_language_discovery_questions(mock_genai_client):
    import json
    from pathlib import Path
    from src.domains.ai.facade.ai import AIFacade
    from src.domains.ai.models.contract.ai import AIQueryRequestContract
    from src.domains.project.operations.membership import ProjectMembershipService
    from src.services.ai.genai_service import GenAIService

    project_facade = ProjectFacade()
    kdg_store = KDGGraphStore()
    membership_service = ProjectMembershipService()

    proj_alpha = "proj-alpha"
    proj_beta = "proj-beta"

    # Cleanup any previous runs
    for p in (proj_alpha, proj_beta):
        try:
            await project_facade.delete_project(p)
        except Exception:
            pass

    # 1. Create projects
    await project_facade.create_project(
        ProjectCreateContract(project_id=proj_alpha, name="Alpha Finance"),
        creator_user_id="alice",
    )
    await project_facade.create_project(
        ProjectCreateContract(project_id=proj_beta, name="Beta Clinical"),
        creator_user_id="alice",
    )

    # 2. Add Bob to proj_alpha only
    membership_service.add_member(proj_alpha, user_id="bob", role="member", added_by="alice")

    # 3. Ingest datasets into proj_alpha
    accounts_csv = Path("tests/fixtures/discovery/accounts.csv").read_bytes()
    await project_facade.ingest_tabular(
        project_id=proj_alpha,
        dataset_name="accounts",
        data_bytes=accounts_csv,
        filename="accounts.csv",
        tier="BRONZE",
    )

    # Ingest bronze_events and gold_kpi for lineage testing in proj_alpha
    await project_facade.ingest_tabular(
        project_id=proj_alpha,
        dataset_name="bronze_events",
        data_bytes=b"id,val\n1,10\n",
        filename="bronze.csv",
        tier="BRONZE",
    )
    await project_facade.ingest_tabular(
        project_id=proj_alpha,
        dataset_name="gold_kpi",
        data_bytes=b"id,kpi\n1,100\n",
        filename="gold.csv",
        tier="GOLD",
    )
    kdg_store.record_pipeline_execution(
        run_id="run-nl-1",
        pipeline_id="pipe-kpi",
        project_id=proj_alpha,
        status="SUCCESS",
        input_datasets=["bronze_events"],
        target_dataset="gold_kpi",
    )

    # 4. Ingest datasets into proj_beta
    patients_csv = Path("tests/fixtures/discovery/patients.csv").read_bytes()
    await project_facade.ingest_tabular(
        project_id=proj_beta,
        dataset_name="patients",
        data_bytes=patients_csv,
        filename="patients.csv",
        tier="BRONZE",
    )
    await project_facade.ingest_tabular(
        project_id=proj_beta,
        dataset_name="silver_vitals",
        data_bytes=b"id,vital\n1,normal\n",
        filename="vitals.csv",
        tier="SILVER",
    )

    # 5. Load and evaluate 20 validation questions
    fixtures_path = Path("tests/fixtures/discovery/nl_questions.json")
    questions = json.loads(fixtures_path.read_text())

    passed_count = 0
    total_count = len(questions)

    for item in questions:
        user_id = item["user"]
        user_ctx = {"sub": user_id, "roles": ["user"]}
        ai_facade = AIFacade(service=GenAIService(client=mock_genai_client), user=user_ctx)

        req = AIQueryRequestContract(prompt=item["question"], user_id=user_id)
        res = await ai_facade.ask(req)
        ans = res.response

        # Check contains
        contains_ok = all(needle in ans for needle in item.get("expected_contains", []))
        # Check not contains
        not_contains_ok = not any(forbidden in ans for forbidden in item.get("expected_not_contains", []))

        if contains_ok and not_contains_ok:
            passed_count += 1
        else:
            print(f"FAILED Question {item['id']}: '{item['question']}' (user: {user_id})")
            print(f"Answer: {ans}")
            print(f"Expected contains: {item.get('expected_contains')}")
            print(f"Expected not contains: {item.get('expected_not_contains')}")

    accuracy = passed_count / total_count
    print(f"Discovery NL Questions Accuracy: {passed_count}/{total_count} ({accuracy * 100:.1f}%)")

    # Cleanup
    for p in (proj_alpha, proj_beta):
        await project_facade.delete_project(p)

    assert accuracy >= 0.85, f"Accuracy {accuracy * 100:.1f}% below 85% threshold (SC-007)"


@pytest.mark.asyncio
async def test_cross_domain_discovery_three_unrelated_domains():
    """SC-008: Discovery works end to end on at least three unrelated data domains without domain-specific config."""
    project_facade = ProjectFacade()
    discovery_facade = DiscoveryFacade()

    proj_health = "proj-domain-healthcare"
    proj_fin = "proj-domain-finance"
    proj_iot = "proj-domain-iot"

    # Cleanup
    for p in (proj_health, proj_fin, proj_iot):
        try:
            await project_facade.delete_project(p)
        except Exception:
            pass

    # 1. Create Projects
    await project_facade.create_project(
        ProjectCreateContract(project_id=proj_health, name="Clinical Trials"),
        creator_user_id="analyst",
    )
    await project_facade.create_project(
        ProjectCreateContract(project_id=proj_fin, name="Core Banking"),
        creator_user_id="analyst",
    )
    await project_facade.create_project(
        ProjectCreateContract(project_id=proj_iot, name="Smart Factory Telemetry"),
        creator_user_id="analyst",
    )

    analyst_ctx = {"sub": "analyst", "roles": ["user"]}

    # 2. Ingest Healthcare domain data
    health_csv = b"subject_id,blood_pressure,diagnosis_date,physician,contact_email\nSUBJ-901,120/80,2026-03-01T08:00:00Z,Dr. Smith,dr.smith@clinic.org\n"
    await project_facade.ingest_tabular(
        project_id=proj_health,
        dataset_name="clinical_vitals",
        data_bytes=health_csv,
        filename="vitals.csv",
        tier="BRONZE",
    )

    # 3. Ingest Finance domain data
    fin_csv = b"account_num,balance,transaction_date,risk_score,currency\nACCT-55443,450000.75,2026-03-01T09:30:00Z,0.92,USD\n"
    await project_facade.ingest_tabular(
        project_id=proj_fin,
        dataset_name="ledger_transactions",
        data_bytes=fin_csv,
        filename="ledger.csv",
        tier="BRONZE",
    )

    # 4. Ingest IoT domain data
    iot_csv = b"device_id,temperature_c,vibration_hz,gateway_ip,recorded_at\nDEV-GW-99,42.5,120.3,192.168.1.10,2026-03-01T10:00:00Z\n"
    await project_facade.ingest_tabular(
        project_id=proj_iot,
        dataset_name="sensor_readings",
        data_bytes=iot_csv,
        filename="sensors.csv",
        tier="BRONZE",
    )

    # 5. Verify structural discovery across all 3 domains
    ws_health = await discovery_facade.get_workspace_knowledge(proj_health, user=analyst_ctx)
    ws_fin = await discovery_facade.get_workspace_knowledge(proj_fin, user=analyst_ctx)
    ws_iot = await discovery_facade.get_workspace_knowledge(proj_iot, user=analyst_ctx)

    assert ws_health is not None
    assert len(ws_health.resources) >= 1
    assert any(a.name == "blood_pressure" for r in ws_health.resources for a in r.attributes)

    assert ws_fin is not None
    assert len(ws_fin.resources) >= 1
    assert any(a.name == "balance" for r in ws_fin.resources for a in r.attributes)

    assert ws_iot is not None
    assert len(ws_iot.resources) >= 1
    assert any(a.name == "gateway_ip" for r in ws_iot.resources for a in r.attributes)

    # 6. Verify cross-project entity resolution works regardless of domain
    ip_corr = await discovery_facade.find_entities(value="192.168.1.10", user=analyst_ctx)
    assert ip_corr.total_projects >= 1
    assert any(m.project_id == proj_iot for m in ip_corr.matches)

    # Cleanup
    for p in (proj_health, proj_fin, proj_iot):
        await project_facade.delete_project(p)



