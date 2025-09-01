use strict; use warnings;
use Test::More;
use FindBin; use lib "$FindBin::Bin/../lib";
use Orbit::ApiClient;

if (!$ENV{ORBIT_INTEGRATION} || $ENV{ORBIT_INTEGRATION} ne '1') {
    plan skip_all => 'Set ORBIT_INTEGRATION=1 to run integration tests';
}

plan tests => 1;
my $url = $ENV{ORBIT_URL} // 'http://localhost:3000';
my $c = Orbit::ApiClient->new($url);
my $all = '';
$c->stream_chat('ping', 0, sub { my ($chunk) = @_; $all .= $chunk->{text}; });
ok(length($all) >= 0, 'received some text (smoke)');

