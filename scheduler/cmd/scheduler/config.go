package main

type Config struct {
	ListenGrpc []string         `mapstructure:"listen_grpc"`
	ListenHttp []string         `mapstructure:"listen_http"`
	PublicHttp []string         `mapstructure:"public_http"`
	LogStash   LogStashConfig   `mapstructure:"logstash"`
	Dashboard  *DashboardConfig `mapstructure:"dashboard"`
}

func (c *Config) GetDashboardUri() string {
	if c.Dashboard != nil {
		return c.Dashboard.GetDashboardUri()
	}
	return ""
}

func (c *Config) GetLogstashUri() string {
	for _, publicUri := range c.PublicHttp {
		return publicUri
	}

	return ""
}
