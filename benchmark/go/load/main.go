// Licensed to the Apache Software Foundation (ASF) under one
// or more contributor license agreements. See the NOTICE file
// distributed with this work for additional information
// regarding copyright ownership. The ASF licenses this file
// to you under the Apache License, Version 2.0 (the
// "License"); you may not use this file except in compliance
// with the License. You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing,
// software distributed under the License is distributed on an
// "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
// KIND, either express or implied. See the License for the
// specific language governing permissions and limitations
// under the License.

// A closed-loop load over Dubbo that adds next to nothing to what it
// measures: each of --concurrency goroutines sends the request body of the
// file --body again as soon as its response comes, over --connections
// connections. A response counts when its status is OK and it holds a
// value. It prints "started" once each connection has answered; calls during
// --warmup are not counted. It prints the result as JSON, as client.py does:
// the calls and errors counted, the calls per second, the CPU microseconds
// of the process for each call meanwhile, and the latency percentiles in
// microseconds, from buckets about 1% wide.
package main

import (
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math"
	"net"
	"os"
	"sort"
	"sync"
	"syscall"
	"time"
)

const (
	headerSize = 16
	// A two-way request in Hessian 2.
	requestFlags = 0xC2
	statusOK     = 20
	// Bucket b holds the latencies of e^(b/100) to e^((b+1)/100) nanoseconds.
	bucketsPerE = 100
)

// The names of the statuses of a response other than OK.
var statuses = map[byte]string{
	30: "CLIENT_TIMEOUT", 31: "SERVER_TIMEOUT", 35: "CHANNEL_INACTIVE", 40: "BAD_REQUEST", 50: "BAD_RESPONSE",
	60: "SERVICE_NOT_FOUND", 70: "SERVICE_ERROR", 80: "SERVER_ERROR", 90: "CLIENT_ERROR",
	100: "SERVER_THREADPOOL_EXHAUSTED_ERROR",
}

var wanted = []float64{50, 90, 99, 99.9}

type connection struct {
	conn net.Conn
	// The frames to send, which the writer sends together as they queue up, as clients do.
	frames chan []byte
	// The outcome of each worker's call in flight, by the worker's index, its request id.
	outcomes map[int64]chan string
}

func main() {
	address := flag.String("address", "127.0.0.1:20880", "the provider to call")
	bodyFile := flag.String("body", "", "the file of the request body")
	concurrency := flag.Int("concurrency", 16, "calls in flight")
	connections := flag.Int("connections", 1, "connections the calls share")
	warmup := flag.Float64("warmup", 3, "seconds before counting")
	duration := flag.Float64("duration", 10, "seconds counted")
	flag.Parse()

	body, err := os.ReadFile(*bodyFile)
	if err != nil {
		panic(err)
	}
	count := min(*connections, *concurrency)
	pool := make([]*connection, count)
	for i := range pool {
		conn, err := net.Dial("tcp", *address)
		if err != nil {
			panic(err)
		}
		pool[i] = &connection{conn: conn, frames: make(chan []byte, *concurrency), outcomes: map[int64]chan string{}}
	}
	frames := make([][]byte, *concurrency)
	for id := range frames {
		frame := make([]byte, headerSize+len(body))
		binary.BigEndian.PutUint16(frame, 0xDABB)
		frame[2] = requestFlags
		binary.BigEndian.PutUint64(frame[4:], uint64(id))
		binary.BigEndian.PutUint32(frame[12:], uint32(len(body)))
		copy(frame[headerSize:], body)
		frames[id] = frame
		pool[id%count].outcomes[int64(id)] = make(chan string, 1)
	}
	for _, each := range pool {
		go each.read()
		go each.write()
	}
	// Each connection answers once before the start.
	for id := range count {
		if outcome := pool[id].call(int64(id), frames[id]); outcome != "" {
			panic(outcome)
		}
	}
	fmt.Println("started")

	counted := time.Now().Add(seconds(*warmup))
	end := counted.Add(seconds(*duration))
	histograms := make([]map[int]int64, *concurrency)
	errors := make([]map[string]int64, *concurrency)
	var group sync.WaitGroup
	for id := range *concurrency {
		histogram, failed := map[int]int64{}, map[string]int64{}
		histograms[id], errors[id] = histogram, failed
		own := pool[id%count]
		group.Add(1)
		go func() {
			defer group.Done()
			for {
				sent := time.Now()
				if !sent.Before(end) {
					return
				}
				outcome := own.call(int64(id), frames[id])
				if sent.Before(counted) {
					continue
				}
				if outcome != "" {
					failed[outcome]++
					continue
				}
				histogram[bucket(time.Since(sent))]++
			}
		}()
	}
	time.Sleep(time.Until(counted))
	cpu := cpuSeconds()
	time.Sleep(time.Until(end))
	cpu = cpuSeconds() - cpu
	group.Wait()

	histogram, failures := map[int]int64{}, map[string]int64{}
	var calls int64
	for id := range *concurrency {
		for key, n := range histograms[id] {
			histogram[key] += n
			calls += n
		}
		for key, n := range errors[id] {
			failures[key] += n
		}
	}
	var cpuPerCall any
	if calls > 0 {
		cpuPerCall = math.Round(cpu/float64(calls)*1e8) / 100
	}
	result := map[string]any{
		"calls":         calls,
		"errors":        failures,
		"rps":           math.Round(float64(calls)/(*duration)*10) / 10,
		"client_cpu_us": cpuPerCall,
		"latency_us":    percentiles(histogram),
	}
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		panic(err)
	}
}

// Send the frame of the worker id and return the outcome of its call: empty for one that succeeded.
func (c *connection) call(id int64, frame []byte) string {
	c.frames <- frame
	return <-c.outcomes[id]
}

// Send the frames as they queue up, those queued together in one write.
func (c *connection) write() {
	var buffer []byte
	for frame := range c.frames {
		buffer = append(buffer[:0], frame...)
	more:
		for {
			select {
			case frame := <-c.frames:
				buffer = append(buffer, frame...)
			default:
				break more
			}
		}
		if _, err := c.conn.Write(buffer); err != nil {
			panic(err)
		}
	}
}

// Read the responses, telling each worker the outcome of its call.
func (c *connection) read() {
	header := make([]byte, headerSize)
	body := make([]byte, 64*1024)
	for {
		if _, err := io.ReadFull(c.conn, header); err != nil {
			panic(err)
		}
		length := int(binary.BigEndian.Uint32(header[12:]))
		if length > len(body) {
			body = make([]byte, length)
		}
		if _, err := io.ReadFull(c.conn, body[:length]); err != nil {
			panic(err)
		}
		outcome, waiting := c.outcomes[int64(binary.BigEndian.Uint64(header[4:]))]
		if header[2]&0x80 != 0 || !waiting {
			// A request of the server, such as a heartbeat, or no call of ours.
			continue
		}
		outcome <- result(header[3], body[:length])
	}
}

func result(status byte, body []byte) string {
	if status != statusOK {
		if name, known := statuses[status]; known {
			return name
		}
		return fmt.Sprintf("status %d", status)
	}
	// The Hessian 2 integer that starts the body: 1 for a value, 4 for a value with attachments.
	if len(body) == 0 || (body[0] != 0x91 && body[0] != 0x94) {
		return "EXCEPTION"
	}
	return ""
}

func seconds(value float64) time.Duration {
	return time.Duration(value * float64(time.Second))
}

func bucket(elapsed time.Duration) int {
	return int(math.Log(math.Max(float64(elapsed.Nanoseconds()), 1)) * bucketsPerE)
}

func microseconds(bucket int) float64 {
	return math.Round(math.Exp((float64(bucket)+0.5)/bucketsPerE)/100) / 10
}

func percentiles(histogram map[int]int64) map[string]float64 {
	keys := make([]int, 0, len(histogram))
	var total int64
	for key, n := range histogram {
		keys = append(keys, key)
		total += n
	}
	sort.Ints(keys)
	result := map[string]float64{}
	var seen int64
	next := 0
	for _, key := range keys {
		seen += histogram[key]
		for next < len(wanted) && float64(seen) >= float64(total)*wanted[next]/100 {
			result[fmt.Sprintf("p%g", wanted[next])] = microseconds(key)
			next++
		}
	}
	if len(keys) > 0 {
		result["max"] = microseconds(keys[len(keys)-1])
	}
	return result
}

func cpuSeconds() float64 {
	var usage syscall.Rusage
	_ = syscall.Getrusage(syscall.RUSAGE_SELF, &usage)
	return float64(usage.Utime.Nano()+usage.Stime.Nano()) / 1e9
}
