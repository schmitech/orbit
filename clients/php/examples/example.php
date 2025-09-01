<?php
require_once __DIR__ . '/../src/ApiClient.php';
use SchmiTech\Orbit\ApiClient;

$url = getenv('ORBIT_URL') ?: 'http://localhost:3000';
$client = new ApiClient($url);
$client->streamChat('Hello from PHP!', true, function($chunk) {
  echo $chunk->text;
  if ($chunk->done) echo "\n";
});

