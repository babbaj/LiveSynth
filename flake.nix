{
  description = "A very basic flake";

  nixConfig = {
    extra-trusted-public-keys = "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZLr6cv/Hm9XgU50cw=";
    extra-substituters = "https://devenv.cachix.org";
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
