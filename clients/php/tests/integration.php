<?php
require_once __DIR__ . '/../src/ApiClient.php';
use SchmiTech\Orbit\ApiClient;

if (getenv('ORBIT_INTEGRATION') !== '1') {
  fwrite(STDERR, "Skipping integration test. Set ORBIT_INTEGRATION=1 to run.\n");
  exit(0);
}

$url = getenv('ORBIT_URL') ?: 'http://localhost:3000';
$client = new ApiClient($url);
$all = '';
$client->streamChat('ping', false, function($chunk) use (&$all) { $all .= $chunk->text; });
if ($all === '') { fwrite(STDERR, "Empty response\n"); exit(1); }
echo "OK\n";
exit(0);

