#!/usr/bin/env perl
use strict; use warnings;
use FindBin; use lib "$FindBin::Bin/../lib";
use Orbit::ApiClient;

my $url = $ENV{ORBIT_URL} // 'http://localhost:3000';
my $c = Orbit::ApiClient->new($url);
$c->stream_chat('Hello from Perl!', 1, sub { my ($chunk) = @_; print $chunk->{text}; print "\n" if $chunk->{done}; });

