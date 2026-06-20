package installer

type SafeOptions struct {
	Options
	ProxySubscriptionURL string `json:"proxy_subscription_url,omitempty"`
}

type SafePlan struct {
	Script          string   `json:"script"`
	Argv            []string `json:"argv"`
	RedactedPreview string   `json:"redacted_preview"`
}

func (o Options) Safe() SafeOptions {
	safe := SafeOptions{Options: o}
	if o.ProxySubscriptionURL != "" {
		safe.Options.ProxySubscriptionURL = Redacted
		safe.ProxySubscriptionURL = Redacted
	}
	return safe
}

func (p CommandPlan) Safe() SafePlan {
	argv := append([]string(nil), p.Argv...)
	for i := 0; i < len(argv)-1; i++ {
		if argv[i] == "--proxy-subscription-url" {
			argv[i+1] = Redacted
		}
	}
	return SafePlan{
		Script:          p.Script,
		Argv:            argv,
		RedactedPreview: p.RedactedPreview,
	}
}
