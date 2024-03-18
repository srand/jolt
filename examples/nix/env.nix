# env.nix

let
  nixpkgs = fetchTarball "https://github.com/NixOS/nixpkgs/tarball/nixos-23.11";
  pkgs = import nixpkgs {};
in

pkgs.mkShell {
  packages = [
    pkgs.go
  ];
}
