package main

type DashboardConfig struct {
	Uri string `mapstructure:"uri"`
}

func (c *DashboardConfig) GetDashboardUri() string {
	return c.Uri
}
