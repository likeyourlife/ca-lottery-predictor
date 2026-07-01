const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const PORT = 8899;
const FRONTEND_DIR = __dirname;
const PYTHON_BIN = '/Users/ioorule/.workbuddy/binaries/python/envs/default/bin/python';
const PREDICTOR_DIR = path.join(__dirname, '..');
const GENERATE_SCRIPT = path.join(FRONTEND_DIR, 'generate_api_data.py');

// MIME types
const MIME_TYPES = {
    '.html': 'text/html',
    '.json': 'application/json',
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
};

// ── Static File Handler ──
function serveStatic(filePath, res) {
    const ext = path.extname(filePath);
    fs.readFile(filePath, (err, data) => {
        if (err) {
            res.writeHead(404, { 'Content-Type': 'text/plain' });
            res.end('Not found');
            return;
        }
        res.writeHead(200, {
            'Content-Type': MIME_TYPES[ext] || 'text/plain',
            'Cache-Control': ext === '.json' ? 'no-cache' : 'public, max-age=3600',
        });
        res.end(data);
    });
}

// ── API: /api/run — Run prediction engine ──
let isRunning = false;
let lastRunResult = null;

function handleApiRun(res) {
    if (isRunning) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'running', message: '预测引擎正在运行中，请稍候...' }));
        return;
    }

    isRunning = true;
    console.log('[API] Starting prediction engine...');

    const proc = spawn(PYTHON_BIN, [GENERATE_SCRIPT], {
        cwd: PREDICTOR_DIR,
        env: { ...process.env, PYTHONPATH: PREDICTOR_DIR },
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => {
        stdout += data.toString();
        console.log('[Python stdout]', data.toString().trim());
    });

    proc.stderr.on('data', (data) => {
        stderr += data.toString();
        console.log('[Python stderr]', data.toString().trim());
    });

    proc.on('close', (code) => {
        isRunning = false;
        const success = code === 0;

        if (success) {
            lastRunResult = {
                status: 'success',
                message: '预测引擎运行完成，数据已更新',
                exitCode: code,
                timestamp: new Date().toISOString(),
            };
            console.log('[API] Prediction engine completed successfully');
        } else {
            lastRunResult = {
                status: 'error',
                message: '预测引擎运行失败',
                exitCode: code,
                stderr: stderr.slice(-500), // last 500 chars of error
                timestamp: new Date().toISOString(),
            };
            console.log('[API] Prediction engine failed with code', code);
        }

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(lastRunResult));
    });

    // Timeout protection: 5 minutes
    proc.on('error', (err) => {
        isRunning = false;
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'error', message: '无法启动预测引擎: ' + err.message }));
    });
}

// ── API: /api/status — Check engine status ──
function handleApiStatus(res) {
    // Check if JSON data files exist
    const requiredFiles = ['prediction.json', 'recent_draws.json', 'daily_accuracy.json'];
    const missingFiles = requiredFiles.filter(f => !fs.existsSync(path.join(FRONTEND_DIR, f)));

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
        isRunning,
        dataReady: missingFiles.length === 0,
        missingFiles,
        lastRun: lastRunResult,
    }));
}

// ── API: /api/predict — Run full prediction pipeline ──
function handleApiPredict(res) {
    if (isRunning) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'running', message: '引擎正在运行中...' }));
        return;
    }

    isRunning = true;
    console.log('[API] Starting full prediction pipeline...');

    // Run daily_pipeline.py which does: init → backtest → predict → save JSON
    const pipelineScript = path.join(PREDICTOR_DIR, 'daily_pipeline.py');
    const proc = spawn(PYTHON_BIN, [pipelineScript], {
        cwd: PREDICTOR_DIR,
        env: { ...process.env, PYTHONPATH: PREDICTOR_DIR },
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => { stdout += data.toString(); });
    proc.stderr.on('data', (data) => { stderr += data.toString(); });

    proc.on('close', (code) => {
        isRunning = false;

        // After pipeline, also regenerate frontend data
        if (code === 0) {
            console.log('[API] Pipeline completed, regenerating frontend data...');
            const genProc = spawn(PYTHON_BIN, [GENERATE_SCRIPT], {
                cwd: PREDICTOR_DIR,
                env: { ...process.env, PYTHONPATH: PREDICTOR_DIR },
            });

            let genStderr = '';
            genProc.stderr.on('data', (data) => { genStderr += data.toString(); });

            genProc.on('close', (genCode) => {
                const success = genCode === 0;
                lastRunResult = {
                    status: success ? 'success' : 'error',
                    message: success ? '预测+数据生成完成' : '数据生成失败',
                    exitCode: genCode,
                    timestamp: new Date().toISOString(),
                };
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify(lastRunResult));
            });
        } else {
            lastRunResult = {
                status: 'error',
                message: '预测管线运行失败',
                exitCode: code,
                stderr: stderr.slice(-500),
                timestamp: new Date().toISOString(),
            };
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(lastRunResult));
        }
    });

    proc.on('error', (err) => {
        isRunning = false;
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'error', message: err.message }));
    });
}

// ── Main HTTP Server ──
const server = http.createServer((req, res) => {
    const url = req.url;

    // API routes
    if (url === '/api/run') {
        handleApiRun(res);
        return;
    }
    if (url === '/api/predict') {
        handleApiPredict(res);
        return;
    }
    if (url === '/api/status') {
        handleApiStatus(res);
        return;
    }

    // Static files
    let filePath;
    if (url === '/' || url === '/index.html') {
        filePath = path.join(FRONTEND_DIR, 'index.html');
    } else {
        filePath = path.join(FRONTEND_DIR, url);
    }

    // Security: only serve files from FRONTEND_DIR
    const resolved = path.resolve(filePath);
    if (!resolved.startsWith(path.resolve(FRONTEND_DIR))) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
    }

    serveStatic(filePath, res);
});

server.listen(PORT, () => {
    console.log(`[Server] Running on http://localhost:${PORT}`);
    console.log(`[Server] API endpoints: /api/run, /api/predict, /api/status`);
    console.log(`[Server] Python: ${PYTHON_BIN}`);
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('[Server] Shutting down...');
    server.close();
    process.exit(0);
});
