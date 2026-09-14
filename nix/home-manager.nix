{ self }:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.edunet;
in
{
  options.services.edunet = import ./options.nix {
    inherit lib;
    defaultPackage = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
    defaultEnvironmentFile = "%h/.config/edunet/check.env";
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = pkgs.stdenv.hostPlatform.isLinux;
        message = "services.edunet requires Linux and systemd.";
      }
      {
        assertion =
          (lib.hasPrefix "/" cfg.environmentFile || lib.hasPrefix "%h/" cfg.environmentFile)
          && !(lib.hasPrefix "/nix/store/" cfg.environmentFile);
        message = "services.edunet.environmentFile must refer to an external absolute path or %h/ path, outside the Nix store.";
      }
    ];
    home.packages = [ cfg.package ];
    systemd.user.services.edunet-check = {
      Unit.Description = "Check campus connectivity and log in when offline";
      Service = {
        Type = "oneshot";
        ExecStart = "${lib.getExe cfg.package} --no-color --timeout ${toString cfg.timeout} login --no-input --require-portal";
        EnvironmentFile = cfg.environmentFile;
        Environment = [ "PYTHONUNBUFFERED=1" ];
        TimeoutStartSec = cfg.serviceTimeout;
        StandardOutput = "journal";
        StandardError = "journal";
      };
    };
    systemd.user.timers.edunet-check = {
      Unit.Description = "Periodically reconnect the campus network";
      Timer = {
        OnStartupSec = cfg.startupDelay;
        OnUnitActiveSec = cfg.interval;
        RandomizedDelaySec = cfg.randomizedDelay;
        AccuracySec = "1s";
        Unit = "edunet-check.service";
      };
      Install.WantedBy = [ "timers.target" ];
    };
  };
}
