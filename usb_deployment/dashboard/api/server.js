// server.js – 대시보드 API (Node.js/Express)
import express from 'express';
import cors from 'cors';
import { exec } from 'child_process';

const app = express();
app.use(cors());
app.use(express.json());

// 봇 ID와 실제 도커 컨테이너 이름 매핑
const ID_MAP = {
    'BTC_30m': 'bot_btc_30m',
    'Bybit_1h': 'bot_bybit_1h',
    'Deploy_15m': 'bot_deploy_15m',
    'Real_5m': 'bot_real_5m',
    'Ultimate_100m': 'bot_ultimate_100m'
};

const BOT_IDS = Object.keys(ID_MAP);

// Docker 명령 실행 헬퍼
function docker(cmd) {
    return new Promise((resolve, reject) => {
        exec(`docker ${cmd}`, (err, stdout, stderr) => {
            if (err) return reject(stderr || err.message);
            resolve(stdout);
        });
    });
}

// 1. 상태 조회
app.get('/status', async (_, res) => {
    try {
        // 실행 중인 컨테이너 이름 조회
        const stdout = await docker('ps --format "{{.Names}}"');
        const runningContainers = stdout.trim().split('\n');

        const status = {};
        for (const [id, containerName] of Object.entries(ID_MAP)) {
            // 실제 데이터(잔액 등)를 얻으려면 파일 조회 로직 필요 (현재는 컨테이너 상태만 표시)
            const isRunning = runningContainers.includes(containerName);
            status[id] = {
                status: isRunning ? 'Running' : 'Stopped',
                // 아래 필드들은 추후 봇이 로그 파일이나 상태 파일을 남기면 읽어서 채워야 함
                balance: isRunning ? '확인 중...' : '-',
                profit: isRunning ? '0.0%' : '-',
                market_price: isRunning ? '' : '-'
            };
        }
        res.json(status);
    } catch (e) {
        console.error(e);
        res.status(500).json({ error: e.toString() });
    }
});

// 2. 봇 시작
app.post('/start/:id', async (req, res) => {
    const { id } = req.params;
    const containerName = ID_MAP[id];
    if (!containerName) return res.status(400).send('Invalid bot');

    try {
        await docker(`start ${containerName}`);
        res.send('ok');
    } catch (e) { res.status(500).send(e.toString()); }
});

// 3. 봇 중지
app.post('/stop/:id', async (req, res) => {
    const { id } = req.params;
    const containerName = ID_MAP[id];
    if (!containerName) return res.status(400).send('Invalid bot');

    try {
        await docker(`stop ${containerName}`);
        res.send('ok');
    } catch (e) { res.status(500).send(e.toString()); }
});

// 4. 로그 조회
app.post('/logs/:id', async (req, res) => {
    const { id } = req.params;
    const containerName = ID_MAP[id];
    if (!containerName) return res.status(400).send('Invalid bot');

    try {
        const out = await docker(`logs --tail 100 ${containerName}`);
        // 로그가 텍스트로 오면 배열로 변환 없이 바로 보내거나 분할 전송
        res.send(out);
    } catch (e) { res.status(500).send(e.toString()); }
});

const PORT = 3000;
app.listen(PORT, () => console.log(`Dashboard API listening on port ${PORT}`));
