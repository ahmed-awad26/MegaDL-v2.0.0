<?php
/**
 * MegaDL — backend-php/api/index.php
 * Central PHP API router — handles all /api/* requests.
 * Place this in backend-php/api/ with an .htaccess that routes to it.
 */

declare(strict_types=1);

// ── CORS headers ─────────────────────────────────────────────
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, X-MegaDL-Client');
header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

// ── Autoload helpers ──────────────────────────────────────────
require_once __DIR__ . '/../utils/helpers.php';
require_once __DIR__ . '/../database/Database.php';
require_once __DIR__ . '/../config/Config.php';

// ── Route ─────────────────────────────────────────────────────
$method = $_SERVER['REQUEST_METHOD'];
$path   = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$path   = preg_replace('#^.*/backend-php/api#', '', $path);
$path   = rtrim($path, '/') ?: '/';
$body   = json_decode(file_get_contents('php://input'), true) ?? [];

$db     = Database::getInstance();
$config = Config::getInstance();

// Router
try {
    route($method, $path, $body, $db, $config);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => $e->getMessage()]);
}

// ─────────────────────────────────────────────────────────────

function restore_orphaned_jobs(Database $db, Config $config): void {
    require_once __DIR__ . '/handlers/download.php';
    $active = $db->getActiveJobs();
    foreach ($active as $job) {
        if (in_array($job['state'], ['running', 'fetching'], true)) {
            if ($job['pid'] && process_alive($job['pid'])) {
                $logFile = dirname(__DIR__, 2) . '/logs/job_' . $job['id'] . '.log';
                start_progress_watcher($job['id'], $job['pid'], $logFile, $db);
            } else {
                // Process dead or unknown — re-queue for retry
                if ($job['state'] === 'running' && $job['pid']) {
                    $db->addLog('Process terminated unexpectedly (server restart)', 'warn', $job['id']);
                }
                $db->updateJob($job['id'], ['state' => 'queued', 'error' => null, 'progress' => 0, 'pid' => null]);
                $db->addLog('Restored after restart — re-queued', 'info', $job['id']);
            }
        } elseif ($job['state'] === 'queued' && !$job['pid']) {
            // Try to start queued jobs that never got a process
            $db->addLog('Starting queued job after restart', 'info', $job['id']);
            start_background_download($job['id'], $job['url'], $job['options'] ?? [], $db, $config);
        }
    }
}

function route(string $method, string $path, array $body, Database $db, Config $config): void
{
    // Ping
    if ($path === '/ping') {
        restore_orphaned_jobs($db, $config);
        echo json_encode(['ok' => true, 'backend' => 'php', 'version' => '2.0.0']);
        return;
    }

    // Info extraction
    if ($path === '/info' && $method === 'POST') {
        require_once __DIR__ . '/handlers/info.php';
        handle_info($body, $config);
        return;
    }

    // Start download
    if ($path === '/download' && $method === 'POST') {
        require_once __DIR__ . '/handlers/download.php';
        handle_download($body, $db, $config);
        return;
    }

    // Batch download
    if ($path === '/batch' && $method === 'POST') {
        require_once __DIR__ . '/handlers/download.php';
        handle_batch($body, $db, $config);
        return;
    }

    // Jobs list
    if ($path === '/jobs' && $method === 'GET') {
        require_once __DIR__ . '/handlers/jobs.php';
        handle_jobs_list($db);
        return;
    }

    // Jobs bulk control
    if ($path === '/jobs/pause-all'  && $method === 'POST') { $db->pauseAllJobs();  echo json_encode(['ok' => true]); return; }
    if ($path === '/jobs/resume-all' && $method === 'POST') { $db->resumeAllJobs(); echo json_encode(['ok' => true]); return; }
    if ($path === '/jobs/cancel-all' && $method === 'POST') { $db->cancelAllJobs(); echo json_encode(['ok' => true]); return; }

    // Single job
    if (preg_match('#^/jobs/([^/]+)$#', $path, $m)) {
        require_once __DIR__ . '/handlers/jobs.php';
        $jobId = $m[1];
        match ($method) {
            'GET'    => handle_job_get($jobId, $db),
            'DELETE' => handle_job_delete($jobId, $db),
            default  => api_error('Method not allowed', 405),
        };
        return;
    }

    // Job actions
    if (preg_match('#^/jobs/([^/]+)/(pause|resume|cancel|retry|logs)$#', $path, $m)) {
        require_once __DIR__ . '/handlers/jobs.php';
        handle_job_action($m[1], $m[2], $db, $config);
        return;
    }

    // History
    if ($path === '/history' && $method === 'GET')    { echo json_encode(['ok' => true, 'history' => $db->getHistory()]); return; }
    if ($path === '/history' && $method === 'DELETE') { $db->clearHistory(); echo json_encode(['ok' => true]); return; }

    // Archive
    if ($path === '/archive' && $method === 'GET')    { echo json_encode(['ok' => true, 'archive' => $db->getArchive()]); return; }
    if ($path === '/archive' && $method === 'DELETE') { $db->clearArchive(); echo json_encode(['ok' => true]); return; }

    // Favorites
    if ($path === '/favorites' && $method === 'GET')  { echo json_encode(['ok' => true, 'favorites' => $db->getFavorites()]); return; }
    if ($path === '/favorites' && $method === 'POST') {
        $jobId = $body['job_id'] ?? '';
        $job   = $db->getJob($jobId);
        if ($job) { $db->addFavorite($job); echo json_encode(['ok' => true]); }
        else api_error('Job not found', 404);
        return;
    }
    if (preg_match('#^/favorites/([^/]+)$#', $path, $m) && $method === 'DELETE') {
        $db->removeFavorite($m[1]);
        echo json_encode(['ok' => true]);
        return;
    }

    // Files
    if ($path === '/files' && $method === 'GET') {
        require_once __DIR__ . '/handlers/files.php';
        handle_files_list($config);
        return;
    }
    if ($path === '/files/delete' && $method === 'POST') {
        require_once __DIR__ . '/handlers/files.php';
        handle_file_delete($body, $config);
        return;
    }
    if ($path === '/files/rename' && $method === 'POST') {
        require_once __DIR__ . '/handlers/files.php';
        handle_file_rename($body, $config);
        return;
    }
    if (preg_match('#^/files/download/(.+)$#', $path, $m)) {
        require_once __DIR__ . '/handlers/files.php';
        handle_file_download($m[1], $config);
        return;
    }

    // Settings
    if ($path === '/settings' && $method === 'GET')  { echo json_encode(array_merge(['ok' => true], $config->all())); return; }
    if ($path === '/settings' && $method === 'POST') { $config->update($body); $config->save(); echo json_encode(['ok' => true]); return; }

    // Logs
    if ($path === '/logs' && $method === 'GET')    { $level = $_GET['level'] ?? null; echo json_encode(['ok' => true, 'logs' => $db->getLogs($level)]); return; }
    if ($path === '/logs' && $method === 'DELETE') { $db->clearLogs(); echo json_encode(['ok' => true]); return; }

    // Diagnostics
    if ($path === '/diagnostics' && $method === 'GET') {
        require_once __DIR__ . '/handlers/diagnostics.php';
        handle_diagnostics($config);
        return;
    }

    // Stats
    if ($path === '/stats' && $method === 'GET') {
        $stats = $db->getStats();
        echo json_encode(array_merge(['ok' => true], $stats));
        return;
    }

    api_error('Not found', 404);
}
