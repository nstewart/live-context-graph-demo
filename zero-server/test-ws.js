const WebSocket = require('ws');

console.log('Testing WebSocket connection to Zero server...');

const ws = new WebSocket('ws://localhost:8090');

ws.on('open', () => {
  console.log('✅ Connected to Zero server');

  // Subscribe to orders collection
  ws.send(JSON.stringify({
    type: 'subscribe',
    collection: 'orders'
  }));
  console.log('📤 Sent subscription request for orders');
});

ws.on('message', (data) => {
  const message = JSON.parse(data.toString());
  console.log('📥 Received message:', message.type);

  if (message.type === 'initial-state') {
    console.log(`✅ Initial state received: ${message.data?.length || 0} orders`);
    if (message.data && message.data.length > 0) {
      console.log('Sample order:', message.data[0]);
    }
  }

  // Close after receiving initial state
  if (message.type === 'initial-state') {
    setTimeout(() => {
      console.log('✅ Test completed successfully!');
      ws.close();
      process.exit(0);
    }, 1000);
  }
});

ws.on('error', (error) => {
  console.error('❌ WebSocket error:', error.message);
  process.exit(1);
});

ws.on('close', () => {
  console.log('🔌 Connection closed');
});

// Timeout after 10 seconds
setTimeout(() => {
  console.error('❌ Test timeout');
  ws.close();
  process.exit(1);
}, 10000);
