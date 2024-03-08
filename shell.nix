let
  nixpkgs = fetchTarball "https://github.com/NixOS/nixpkgs/tarball/nixos-23.11";
  pkgs = import nixpkgs {};

  python3 = pkgs.python3.withPackages(ps: with ps; [
  ]);
in

pkgs.mkShell {
  packages = [
    pkgs.delve
    pkgs.go
    pkgs.grpc
    pkgs.protobuf
    pkgs.protoc-gen-go
    pkgs.protoc-gen-go-grpc
  ];

  # Environment variables
  PYTHONPATH = "${python3}/${python3.sitePackages}";
  SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt;

  shellHook =
  ''
    [ -e ~/workspace/setup ] && . ~/workspace/setup
  '';
}
