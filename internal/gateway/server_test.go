package gateway

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/coder/websocket"

	"github.com/lixuanqun/voice-realtime/internal/config"
	"github.com/lixuanqun/voice-realtime/internal/providers"
)

// stubUpstream records client events forwarded by the gateway and blocks in
// ReadServerEvent so the session stays alive for the duration of the test.
type stubUpstream struct {
	events chan []byte
}

func (u *stubUpstream) WriteClientEvent(ctx context.Context, raw []byte) error {
	u.events <- raw
	return nil
}

func (u *stubUpstream) ReadServerEvent(ctx context.Context) ([]byte, error) {
	<-ctx.Done()
	return nil, ctx.Err()
}

func (u *stubUpstream) Close() error { return nil }

type stubProvider struct{ up *stubUpstream }

func (p *stubProvider) Name() string { return "zhipu" }

func (p *stubProvider) Dial(ctx context.Context, cfg providers.ConnectConfig) (providers.UpstreamConn, error) {
	return p.up, nil
}

// TestRealtimeAcceptsLargeAudioAppends is the regression test for #9: a
// 48,000-byte input_audio_buffer.append encodes to a ~64 KB message, which
// coder/websocket's default 32 KiB read limit rejected, tearing down the
// session on the first audio chunk.
func TestRealtimeAcceptsLargeAudioAppends(t *testing.T) {
	up := &stubUpstream{events: make(chan []byte, 8)}
	// The gateway looks providers up by name; the stub shadows zhipu for the
	// lifetime of this test binary and never touches the network.
	providers.Register(&stubProvider{up: up})

	srv := httptest.NewServer(New(&config.Config{ZhipuAPIKey: "test-key"}, nil).Handler())
	defer srv.Close()

	ctx := context.Background()
	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/v1/realtime?provider=zhipu&model=glm-realtime-flash"
	conn, _, err := websocket.Dial(ctx, wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer conn.Close(websocket.StatusNormalClosure, "test done")

	payload, err := json.Marshal(map[string]string{
		"type":  "input_audio_buffer.append",
		"audio": strings.Repeat("a", 48_000), // 64,000 base64 chars
	})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if err := conn.Write(ctx, websocket.MessageText, payload); err != nil {
		t.Fatalf("write: %v", err)
	}

	select {
	case got := <-up.events:
		if len(got) != len(payload) {
			t.Fatalf("forwarded event truncated: got %d bytes, want %d", len(got), len(payload))
		}
	case <-time.After(5 * time.Second):
		t.Fatal("gateway did not forward the ~64 KB append (read limit still at the 32 KiB default?)")
	}
}
