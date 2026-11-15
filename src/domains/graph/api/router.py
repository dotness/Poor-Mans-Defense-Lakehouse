from fastapi import APIRouter, Query
from src.domains.graph.facade.graph import GraphFacade
from src.domains.graph.models.contract.graph import (
    GraphNodeContract,
    GraphEdgeContract,
    OsintImportRequestContract,
    OsintImportResultContract,
    RelatedEntitiesResultContract,
)

router = APIRouter(prefix="/api/v1/graph", tags=["Knowledge Graph"])


@router.post("/node")
async def add_node(node: GraphNodeContract):
    """Upserts a graph node into Memgraph."""
    facade = GraphFacade()
    success = await facade.add_node(node)
    return {"success": success}


@router.post("/edge")
async def add_edge(edge: GraphEdgeContract):
    """Upserts a directed relationship into Memgraph."""
    facade = GraphFacade()
    success = await facade.add_edge(edge)
    return {"success": success}


@router.post("/import-osint", response_model=OsintImportResultContract)
async def import_osint(import_req: OsintImportRequestContract):
    """Parses and ingests SpiderFoot reconnaissance JSON data."""
    facade = GraphFacade()
    return await facade.import_spiderfoot_json(import_req.raw_json_data)


@router.get("/related", response_model=RelatedEntitiesResultContract)
async def get_related_entities(term: str = Query(..., description="Query term to search for related graph entities")):
    """Retrieves correlated nodes and edges for intelligence analysis."""
    facade = GraphFacade()
    return facade.find_related_entities(term)
