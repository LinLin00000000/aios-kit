package installer

import "testing"

func TestPlatformDefaultsWindowsCoreOnly(t *testing.T) {
	opts := PlatformDefaults(PlatformWindows)
	if opts.Proxy != ChoiceNo || opts.ProxyTun || opts.ResetSources || opts.WithDevEnv || opts.WithHermes || opts.WithAIOps {
		t.Fatalf("windows defaults should be core-only: %#v", opts)
	}
	if opts.AddToPath != ChoiceYes || opts.Target != TargetUniversal || opts.Mode != ModeCopy {
		t.Fatalf("windows should preserve core defaults: %#v", opts)
	}
}

func TestCapabilitiesForPlatformFiltersWindowsAddons(t *testing.T) {
	caps := CapabilitiesForPlatform(PlatformWindows)
	seenCore := false
	for _, cap := range caps {
		if cap.Layer == "core" && cap.Supported {
			seenCore = true
		}
		if cap.Layer == "addon" && cap.Supported {
			t.Fatalf("windows should not expose addon capability %s", cap.ID)
		}
	}
	if !seenCore {
		t.Fatalf("expected at least one supported windows core capability")
	}
}

func TestCapabilitiesForPlatformLinuxIncludesAddons(t *testing.T) {
	if !SupportsAddon(PlatformLinux, "service-24x7") || !SupportsAddon(PlatformLinux, "proxy") {
		t.Fatalf("linux should expose server add-ons")
	}
	if SupportsAddon(PlatformWindows, "service-24x7") {
		t.Fatalf("windows should not expose systemd service add-on")
	}
}
