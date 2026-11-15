#!/usr/bin/env node
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

async function renderPdf(inputHtmlPath, outputPdfPath, docTitle = 'Poor Man\'s Artemis.IA', isMaster = false) {
    const absInput = path.resolve(inputHtmlPath);
    const absOutput = path.resolve(outputPdfPath);

    fs.mkdirSync(path.dirname(absOutput), { recursive: true });

    // Pick a free or random port to avoid conflicts
    const port = 9333 + Math.floor(Math.random() * 500);

    // Launch Chromium headless with remote debugging
    const chrome = spawn('chromium', [
        '--headless',
        '--disable-gpu',
        '--no-sandbox',
        `--remote-debugging-port=${port}`
    ]);

    let versionData = null;
    for (let i = 0; i < 30; i++) {
        try {
            const res = await fetch(`http://127.0.0.1:${port}/json/version`);
            if (res.ok) {
                versionData = await res.json();
                break;
            }
        } catch (e) {
            await new Promise(r => setTimeout(r, 200));
        }
    }

    if (!versionData) {
        chrome.kill();
        throw new Error(`Failed to connect to Chromium CDP on port ${port}`);
    }

    try {
        const targetRes = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' });
        const target = await targetRes.json();
        const ws = new WebSocket(target.webSocketDebuggerUrl);

        await new Promise((resolve, reject) => {
            ws.onopen = resolve;
            ws.onerror = reject;
        });

        let msgId = 1;
        function send(method, params = {}) {
            return new Promise((resolve, reject) => {
                const curId = msgId++;
                const handler = (event) => {
                    const msg = JSON.parse(event.data);
                    if (msg.id === curId) {
                        ws.removeEventListener('message', handler);
                        if (msg.error) {
                            reject(new Error(msg.error.message || JSON.stringify(msg.error)));
                        } else {
                            resolve(msg.result);
                        }
                    }
                };
                ws.addEventListener('message', handler);
                ws.send(JSON.stringify({ id: curId, method, params }));
            });
        }

        await send('Page.enable');
        await send('Runtime.enable');

        await send('Page.navigate', { url: `file://${absInput}` });

        // Wait for page ready (window.__READY__ === true)
        let ready = false;
        let lastError = null;
        for (let i = 0; i < 150; i++) { // up to 30 seconds
            const evalRes = await send('Runtime.evaluate', {
                expression: '({ ready: window.__READY__ === true, count: window.__DIAGRAM_COUNT__ || 0, errors: window.__RENDER_ERRORS__ || 0 })',
                returnByValue: true
            });
            if (evalRes && evalRes.result && evalRes.result.value) {
                const val = evalRes.result.value;
                if (val.ready) {
                    ready = true;
                    console.log(`Rendered ${val.count} diagram(s) with ${val.errors} error(s) for ${path.basename(outputPdfPath)}`);
                    break;
                }
            }
            await new Promise(r => setTimeout(r, 200));
        }

        if (!ready) {
            console.warn(`Warning: Timeout waiting for window.__READY__ in ${inputHtmlPath}. Printing current page state.`);
        }

        // Additional settling pause for font rendering and SVG layout stabilization
        await new Promise(r => setTimeout(r, 400));

        const headerHtml = `
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 7.5pt; color: #64748b; width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 0 16mm; border-bottom: 1px solid #cbd5e1; margin-bottom: 3mm;">
                <span style="font-weight: 600; color: #0284c7;">Poor Man's Defense Lakehouse</span>
                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 65%;">${docTitle}</span>
            </div>
        `;

        const footerHtml = `
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 7.5pt; color: #64748b; width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 0 16mm; border-top: 1px solid #cbd5e1; margin-top: 3mm;">
                <span>Technical Architecture Manual • Print Edition</span>
                <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
            </div>
        `;

        const pdfRes = await send('Page.printToPDF', {
            printBackground: true,
            displayHeaderFooter: true,
            headerTemplate: headerHtml,
            footerTemplate: footerHtml,
            paperWidth: 8.27,   // A4: 210mm
            paperHeight: 11.69, // A4: 297mm
            marginTop: 0.75,    // inches
            marginBottom: 0.75, // inches
            marginLeft: 0.65,   // inches
            marginRight: 0.65,  // inches
            preferCSSPageSize: false,
            generateDocumentOutline: true
        });

        fs.writeFileSync(absOutput, Buffer.from(pdfRes.data, 'base64'));
        const stat = fs.statSync(absOutput);
        console.log(`Generated: ${absOutput} (${(stat.size / 1024).toFixed(1)} KB)`);

        ws.close();
    } finally {
        chrome.kill();
    }
}

if (require.main === module) {
    const args = process.argv.slice(2);
    if (args.length < 2) {
        console.log('Usage: node pdf_renderer.js <input.html> <output.pdf> [docTitle]');
        process.exit(1);
    }
    const [inputHtml, outputPdf, docTitle] = args;
    renderPdf(inputHtml, outputPdf, docTitle || 'Poor Man\'s Artemis.IA')
        .catch(err => {
            console.error('Error rendering PDF:', err);
            process.exit(1);
        });
}

module.exports = { renderPdf };

