package Orbit::ApiClient;
use strict; use warnings;
use Mojo::UserAgent;
use JSON::PP 'decode_json';

sub new {
  my ($class, $api_url, $api_key, $session_id) = @_;
  bless { api_url => $api_url, api_key => $api_key, session_id => $session_id }, $class;
}

sub endpoint {
  my ($self) = @_;
  return $self->{api_url} =~ /\/v1\/chat$/ ? $self->{api_url} : $self->{api_url} =~ s{/+$}{}r . '/v1/chat';
}

sub stream_chat {
  my ($self, $message, $stream, $on_chunk) = @_;
  my $ua = Mojo::UserAgent->new;
  my %headers = (
    'Content-Type' => 'application/json',
    'Accept' => $stream ? 'text/event-stream' : 'application/json',
    'X-Request-ID' => time
  );
  $headers{'X-API-Key'} = $self->{api_key} if $self->{api_key};
  $headers{'X-Session-ID'} = $self->{session_id} if $self->{session_id};
  my $body = sprintf('{"messages":[{"role":"user","content":"%s"}],"stream":%s}', _escape($message), $stream ? 'true' : 'false');

  my $tx = $ua->build_tx(POST => $self->endpoint => \%headers => $body);
  $ua->start_p($tx)->then(sub {
    my ($tx) = @_;
    my $res = $tx->res;
    die 'HTTP error ' . $res->code unless $res->is_success;
    if (!$stream) {
      my $json = eval { decode_json($res->body) };
      my $text = $json && $json->{response} ? $json->{response} : $res->body;
      $on_chunk->({ text => $text, done => 1 }) if $on_chunk;
      return;
    }
    my $buffer = '';
    $res->content->on(read => sub {
      my ($content, $bytes) = @_;
      $buffer .= $bytes;
      while ($buffer =~ s/^(.*?)(\n)//) {
        my $line = $1; $line =~ s/^\s+|\s+$//g; next unless length $line;
        if ($line =~ /^data: /) {
          my $json = $'; $json =~ s/^\s+|\s+$//g;
          if ($json eq '' || $json eq '[DONE]') { $on_chunk->({ text => '', done => 1 }) if $on_chunk; next; }
          my $obj = eval { decode_json($json) };
          if ($obj && $obj->{response}) {
            my $done = $obj->{done} ? 1 : 0;
            $on_chunk->({ text => $obj->{response}, done => $done }) if $on_chunk;
            $on_chunk->({ text => '', done => 1 }) if $done && $on_chunk;
          } else {
            $on_chunk->({ text => $json, done => 0 }) if $on_chunk;
          }
        } else {
          $on_chunk->({ text => $line, done => 0 }) if $on_chunk;
        }
      }
    });
  })->catch(sub { die shift });
}

sub _escape {
  my ($s) = @_;
  $s =~ s/\\/\\\\/g; $s =~ s/"/\\\"/g; $s =~ s/\n/\\n/g; return $s;
}

1;

