package main

import (
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

func NewAdminClient() protocol.AdministrationClient {
	return protocol.NewAdministrationClient(NewSchedulerConn())
}
