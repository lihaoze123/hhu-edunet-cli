{
  self,
  nixpkgs,
  home-manager,
  system,
  pkgs,
}:
let
  inherit (nixpkgs) lib;
  home =
    enabled: extra:
    (home-manager.lib.homeManagerConfiguration {
      inherit pkgs;
      modules = [
        self.homeManagerModules.default
        {
          home.username = "edunet-test";
          home.homeDirectory = "/home/edunet-test";
          home.stateVersion = "26.05";
          services.edunet = {
            enable = enabled;
          }
          // extra;
        }
      ];
    }).config;
  os =
    enabled: extra:
    (lib.nixosSystem {
      inherit system;
      modules = [
        self.nixosModules.default
        {
          system.stateVersion = "26.05";
          services.edunet = {
            enable = enabled;
          }
          // extra;
        }
      ];
    }).config;
  hm = home true {
    interval = "5min";
    timeout = 12;
  };
  nixos = os true { environmentFile = "/run/secrets/edunet"; };
  valid = config: lib.all (a: a.assertion) config.assertions;
in
assert !((home false { }).systemd.user.services ? edunet-check);
assert !((os false { }).systemd.services ? edunet-check);
assert valid hm;
assert
  !(builtins.tryEval (home true { environmentFile = "/nix/store/fake-secret"; }).home.username)
  .success;
assert
  hm.systemd.user.services.edunet-check.Service.EnvironmentFile == "%h/.config/edunet/check.env";
assert hm.systemd.user.timers.edunet-check.Timer.OnUnitActiveSec == "5min";
assert lib.hasInfix "--timeout 12 login --no-input --require-portal" (
  lib.concatStringsSep " " hm.systemd.user.services.edunet-check.Service.ExecStart
);
assert nixos.systemd.services.edunet-check.serviceConfig.DynamicUser;
assert nixos.systemd.services.edunet-check.serviceConfig.EnvironmentFile == "/run/secrets/edunet";
assert nixos.systemd.timers.edunet-check.wantedBy == [ "timers.target" ];
pkgs.runCommand "edunet-module-checks" { } ''
  touch "$out"
''
