{
  description = "A very basic flake";

  nixConfig = {
    extra-trusted-public-keys = "babbaj.cachix.org-1:lmq/0FXqmMccEP0kUz2gnAks2BtlS4NGTDh48bBpax4=";
    extra-substituters = "https://babbaj.cachix.org";
  };

  outputs = { self, nixpkgs }:
  let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      config.allowUnfree = true; # cuda
      inherit system;
    };
  in
  {
    packages.x86_64-linux.whisper = pkgs.openai-whisper.override({torch = pkgs.python3.pkgs.torchWithCuda;});

    devShells.${system}.default = let
      deps = p: with p; [
        (openai-whisper.override({torch = torchWithCuda;}))
        pynput
      ];
      python-env = (pkgs.python3.withPackages deps);
    in pkgs.mkShell rec {
      venvDir = ".venv";
      packages = with pkgs; [
        python3.pkgs.venvShellHook
      ];
      postShellHook = let prefix = pkgs.python3.libPrefix; in ''
        ln -sf ${python-env}/lib/${prefix}/site-packages/* ${venvDir}/lib/${prefix}/site-packages
      '';
    };
  };
}
