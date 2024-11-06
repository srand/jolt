package utils

import "sync"

type plainMutex struct {
	sync.RWMutex
}

func NewRWMutex() *plainMutex {
	return &plainMutex{}
}
