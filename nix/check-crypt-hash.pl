# Check that a crypt hash is usable by libxcrypt (reqs R-A2; design D2,
# plans/2026-11-10T140423Z-root-password-design.md).
#
# Usage: perl check-crypt-hash.pl HASH_FILE
# Prints the hash and exits 0 when it is usable, else exits 1 with a message
# that does not echo the value.
#
# The MCF pattern in nix/site.nix only checks the shape.  libxcrypt is the
# authority: crypt(probe, HASH) recomputes a hash with HASH's setting.  HASH is
# usable iff that succeeds, has the same length, and agrees with HASH up to the
# digest (the text before the last "$").  Invalid parameters make crypt fail
# (Codex on #345: `$y$invalid$salt$hash`); a truncated or padded digest changes
# the length.  Perl's crypt is nixpkgs' libxcrypt (verified 2026-11-10: it
# computes yescrypt and verifies the test hash).
use strict;
use warnings;

my ($file) = @ARGV;
die "usage: $0 HASH_FILE\n" unless defined $file;
open(my $fh, '<', $file) or die "cannot read $file: $!\n";
local $/;
my $hash = <$fh>;
close($fh);

sub reject {
    print STDERR "pre-nixos: rootHashedPassword is not a usable crypt hash ($_[0]);"
      . " make one with `mkpasswd -m yescrypt`\n";
    exit 1;
}

reject("empty") if !defined $hash || $hash eq '';
reject("more than one line") if $hash =~ /\n/;
my $recomputed = crypt("pre-nixos-probe", $hash);
reject("libxcrypt rejects its setting") if !defined $recomputed || $recomputed =~ /^\*/;
reject("wrong digest length") if length($recomputed) != length($hash);
my ($want_setting) = $hash =~ /^(.*)\$/s;
my ($got_setting) = $recomputed =~ /^(.*)\$/s;
reject("setting not preserved") if !defined $want_setting || !defined $got_setting || $want_setting ne $got_setting;
print $hash;
exit 0;
