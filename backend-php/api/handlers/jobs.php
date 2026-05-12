<?php
/**
 * MegaDL — api/handlers/jobs.php
 */
declare(strict_types=1);

function handle_jobs_list(Database $db): void {
    $filter = $_GET['filter'] ?? 'all';
    $sort   = $_GET['sort']   ?? 'date_desc';
    $q      = $_GET['q']      ?? '';
    api_ok(['jobs' => $db->getJobs($filter, $sort, $q)]);
}

function handle_job_get(string $jobId, Database $db): void {
    $job = $db->getJob($jobId);
    $job ? api_ok(['job' => $job]) : api_error('Job not found', 404);
}

function handle_job_delete(string $jobId, Database $db): void {
    $db->deleteJob($jobId);
    api_ok(['deleted' => $jobId]);
}

function handle_job_action(string $jobId, string $action, Database $db, Config $config): void {
    switch ($action) {
        case 'pause':
            $job = $db->getJob($jobId);
            if ($job && $job['pid']) {
                if (PHP_OS_FAMILY !== 'Windows') posix_kill($job['pid'], SIGSTOP);
            }
            $db->updateJob($jobId, ['state' => 'paused']);
            api_ok();
            break;

        case 'resume':
            $job = $db->getJob($jobId);
            if ($job && $job['pid'] && PHP_OS_FAMILY !== 'Windows') {
                posix_kill($job['pid'], SIGCONT);
                $db->updateJob($jobId, ['state' => 'running']);
            } else {
                // Re-queue
                $db->updateJob($jobId, ['state' => 'queued']);
                if ($job) {
                    require_once __DIR__ . '/download.php';
                    start_background_download($jobId, $job['url'], $job['options'] ?? [], $db, $config);
                }
            }
            api_ok();
            break;

        case 'cancel':
            $job = $db->getJob($jobId);
            if ($job && $job['pid']) {
                if (PHP_OS_FAMILY === 'Windows') {
                    shell_exec("taskkill /PID {$job['pid']} /F 2>NUL");
                } else {
                    posix_kill($job['pid'], SIGTERM);
                }
            }
            $db->updateJob($jobId, ['state' => 'cancelled']);
            api_ok();
            break;

        case 'retry':
            $db->updateJob($jobId, ['state' => 'queued', 'error' => null, 'progress' => 0]);
            $job = $db->getJob($jobId);
            if ($job) {
                require_once __DIR__ . '/download.php';
                start_background_download($jobId, $job['url'], $job['options'] ?? [], $db, $config);
            }
            api_ok();
            break;

        case 'logs':
            $logs = $db->getLogs(null, 500, $jobId);
            $text = implode("\n", array_map(fn($l) => "[{$l['time']}] {$l['message']}", $logs));
            api_ok(['logs' => $text, 'entries' => $logs]);
            break;

        default:
            api_error('Unknown action', 400);
    }
}
