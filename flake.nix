{
  description = "edunet-cli: campus ePortal authentication with uv-locked dependencies";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      home-manager,
      pyproject-nix,
      uv2nix,
      pyproject-build-systems,
    }:
    let
      inherit (nixpkgs) lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = lib.genAttrs systems;
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
      overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
      environments = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          pythonSet =
            (pkgs.callPackage pyproject-nix.build.packages {
              python = pkgs.python313;
            }).overrideScope
              (
                lib.composeManyExtensions [
                  pyproject-build-systems.overlays.wheel
                  overlay
                ]
              );
          runtime = pythonSet.mkVirtualEnv "edunet-runtime" workspace.deps.default;
          testEnv = pythonSet.mkVirtualEnv "edunet-tests" workspace.deps.all;
          editableSet = pythonSet.overrideScope (
            lib.composeManyExtensions [
              (workspace.mkEditablePyprojectOverlay {
                root = "$EDUNET_REPO_ROOT";
              })
              (final: prev: {
                edunet-cli = prev.edunet-cli.overrideAttrs (old: {
                  nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ final.resolveBuildSystem { editables = [ ]; };
                });
              })
            ]
          );
          devEnv = editableSet.mkVirtualEnv "edunet-development" workspace.deps.all;
          inherit (pkgs.callPackages pyproject-nix.build.util { }) mkApplication;
          package =
            (mkApplication {
              venv = runtime;
              package = pythonSet.edunet-cli;
            }).overrideAttrs
              (old: {
                postInstall = (old.postInstall or "") + ''
                  mkdir -p "$out/share/edunet/systemd"
                  cp ${./contrib/systemd}/* "$out/share/edunet/systemd/"
                  substituteInPlace "$out/share/edunet/systemd/edunet-check.service" \
                    --replace-fail '%h/.local/bin/edunet' "$out/bin/edunet"
                '';
                meta = (old.meta or { }) // {
                  description = "Campus ePortal login and logout CLI";
                  license = lib.licenses.mit;
                  mainProgram = "edunet";
                };
              });
        in
        {
          inherit
            pkgs
            pythonSet
            testEnv
            devEnv
            package
            ;
        }
      );
    in
    {
      nixosModules.default = self.nixosModules.edunet;
      nixosModules.edunet = import ./nix/nixos.nix { inherit self; };
      homeManagerModules.default = self.homeManagerModules.edunet;
      homeManagerModules.edunet = import ./nix/home-manager.nix { inherit self; };

      packages = forAllSystems (system: {
        default = environments.${system}.package;
        edunet = environments.${system}.package;
      });
      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/edunet";
          meta.description = "Campus ePortal CLI";
        };
        edunet = self.apps.${system}.default;
      });
      devShells = forAllSystems (
        system:
        let
          env = environments.${system};
        in
        {
          default = env.pkgs.mkShell {
            packages = [
              env.devEnv
              env.pkgs.uv
              env.pkgs.nixfmt
            ];
            UV_NO_SYNC = "1";
            UV_PYTHON = env.pythonSet.python.interpreter;
            UV_PYTHON_DOWNLOADS = "never";
            shellHook = ''
              unset PYTHONPATH
              export EDUNET_REPO_ROOT="$PWD"
            '';
          };
        }
      );
      checks = forAllSystems (
        system:
        let
          env = environments.${system};
        in
        {
          tests =
            env.pkgs.runCommand "edunet-checks"
              {
                nativeBuildInputs = [ env.testEnv ];
              }
              ''
                cp -r ${self}/. .
                chmod -R u+w .
                ruff check .
                ruff format --check .
                mypy
                pytest -q
                edunet --version
                touch "$out"
              '';
        }
        // lib.optionalAttrs env.pkgs.stdenv.hostPlatform.isLinux {
          modules = import ./nix/checks.nix {
            inherit
              self
              nixpkgs
              home-manager
              system
              ;
            pkgs = env.pkgs;
          };
        }
      );
      formatter = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        pkgs.writeShellApplication {
          name = "edunet-nixfmt";
          runtimeInputs = [ pkgs.nixfmt ];
          text = ''
            if [ "$#" -eq 0 ]; then
              set -- flake.nix nix/*.nix
            fi
            exec nixfmt "$@"
          '';
        }
      );
    };
}
