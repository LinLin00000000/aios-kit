package installer

import (
	"strings"
	"testing"
)

func TestSafeOptionsRedactsSubscriptionURL(t *testing.T) {
	opts := DefaultOptions()
	opts.ProxySubscriptionURL = "https://example.com/sub?placeholder=PRIVATE-VALUE"
	safe := opts.Safe()
	if safe.Options.ProxySubscriptionURL != Redacted || safe.ProxySubscriptionURL != Redacted {
		t.Fatalf("safe options did not redact subscription URL: %#v", safe)
	}
}

func TestSafePlanRedactsArgv(t *testing.T) {
	opts := DefaultOptions()
	opts.ProxySubscriptionURL = "https://example.com/sub?placeholder=PRIVATE-VALUE"
	plan, err := NewCommandPlan("./install.sh", opts)
	if err != nil {
		t.Fatal(err)
	}
	safe := plan.Safe()
	joined := strings.Join(safe.Argv, " ") + " " + safe.RedactedPreview
	if strings.Contains(joined, "PRIVATE-VALUE") {
		t.Fatalf("safe plan leaked private value: %s", joined)
	}
	if !strings.Contains(joined, Redacted) {
		t.Fatalf("safe plan missing redaction marker: %s", joined)
	}
}
