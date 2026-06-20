package installer

import "testing"

func TestDefaultOptionsValidate(t *testing.T) {
	opts := DefaultOptions()
	if err := opts.Validate(); err != nil {
		t.Fatalf("default options should validate: %v", err)
	}
}

func TestValidateRejectsInvalidChoices(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*Options)
	}{
		{"empty root", func(o *Options) { o.Root = "" }},
		{"bad add-to-path", func(o *Options) { o.AddToPath = "maybe" }},
		{"bad proxy", func(o *Options) { o.Proxy = "sometimes" }},
		{"bad proxy auto env", func(o *Options) { o.ProxyAutoEnv = "sometimes" }},
		{"empty mihomo version", func(o *Options) { o.MihomoVersion = "" }},
		{"bad target", func(o *Options) { o.Target = "codex" }},
		{"bad mode", func(o *Options) { o.Mode = "move" }},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			opts := DefaultOptions()
			tt.mutate(&opts)
			if err := opts.Validate(); err == nil {
				t.Fatalf("expected validation error")
			}
		})
	}
}
