// =============================================================================
// BYRDHOUSE BACKEND SERVER v1.0
// Stripe Payments + Ollama AI + User Management
// =============================================================================

require('dotenv').config();
const express = require('express');
const cors = require('cors');
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
const axios = require('axios');

const app = express();
const PORT = process.env.PORT || 3001;

// =============================================================================
// MIDDLEWARE
// =============================================================================

app.use(cors());
app.use(express.json());

// Track API usage
const trackAPIUsage = (endpoint, userId) => {
  console.log(`[API] ${endpoint} - User: ${userId || 'anonymous'} - ${new Date().toISOString()}`);
};

// =============================================================================
// STRIPE - Create Checkout Session
// =============================================================================

app.post('/api/create-checkout-session', async (req, res) => {
  try {
    const { priceId, userId, userEmail, tier } = req.body;

    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      customer_email: userEmail,
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: `${process.env.FRONTEND_URL}/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${process.env.FRONTEND_URL}/dashboard?cancelled=true`,
      metadata: {
        userId: userId,
        tier: tier
      }
    });

    console.log(`[STRIPE] Checkout created - Session: ${session.id} - Tier: ${tier}`);
    res.json({ sessionId: session.id, url: session.url });

  } catch (error) {
    console.error('[STRIPE ERROR]', error.message);
    res.status(500).json({ error: error.message });
  }
});

// =============================================================================
// STRIPE - Create Customer Portal Session
// =============================================================================

app.post('/api/create-portal-session', async (req, res) => {
  try {
    const { customerId } = req.body;

    const session = await stripe.billingPortal.sessions.create({
      customer: customerId,
      return_url: process.env.FRONTEND_URL
    });

    res.json({ url: session.url });

  } catch (error) {
    console.error('[STRIPE ERROR]', error.message);
    res.status(500).json({ error: error.message });
  }
});

// =============================================================================
// STRIPE - Webhook Handler
// =============================================================================

app.post('/api/webhook', express.raw({ type: 'application/json' }), async (req, res) => {
  const sig = req.headers['stripe-signature'];
  let event;

  try {
    event = stripe.webhooks.constructEvent(req.body, sig, process.env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    console.error('[WEBHOOK ERROR]', err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  // Handle successful payment
  if (event.type === 'checkout.session.completed') {
    const session = event.data.object;
    console.log(`[WEBHOOK] Payment completed - Customer: ${session.customer_email} - Tier: ${session.metadata.tier}`);
    
    // Here you would update your database
    // Example: await db.users.update({ stripeCustomerId: session.customer }, { where: { email: session.customer_email } })
  }

  // Handle subscription cancellation
  if (event.type === 'customer.subscription.deleted') {
    const subscription = event.data.object;
    console.log(`[WEBHOOK] Subscription deleted - ${subscription.id}`);
  }

  res.json({ received: true });
});

// =============================================================================
// OLLAMA via ODYSSEUS GATEWAY — OpenAI-compatible /v1/chat endpoint
// Routes through your local Odysseus server which proxies to Ollama.
// This gives ByrdHouse: streaming, function calling, any model, smart-home tools.
// =============================================================================

const ODYSSEUS_URL = process.env.ODYSSEUS_URL || 'http://localhost:3000';
const DEFAULT_MODEL = process.env.ODYSSEUS_MODEL || 'llama3.2:latest';

// Proxy request to Odysseus OpenAI-compatible gateway
async function ollamaChat(messages, { model = DEFAULT_MODEL, stream = false, temperature = 0.7, max_tokens = 2048 } = {}) {
  const response = await axios.post(`${ODYSSEUS_URL}/v1/chat/completions`, {
    model,
    messages,
    stream,
    temperature,
    max_tokens,
  }, {
    timeout: stream ? 120_000 : 60_000,
    responseType: stream ? 'stream' : 'json',
  });
  return response.data;
}

// Non-streaming chat (backward-compatible)
app.post('/api/chat', async (req, res) => {
  try {
    const { message, userId, model, temperature } = req.body;
    trackAPIUsage('/api/chat', userId);

    const data = await ollamaChat(
      [{ role: 'user', content: message }],
      { model, temperature }
    );

    const response = data.choices?.[0]?.message?.content || '';
    const usedModel = data.model || DEFAULT_MODEL;

    console.log(`[ODYSSEUS] Chat — User: ${userId} — Model: ${usedModel} — Resp: ${response.substring(0, 60)}...`);
    res.json({ response, model: usedModel });

  } catch (error) {
    console.error('[ODYSSEUS ERROR]', error.message);

    // Graceful fallback — don't crash ByrdHouse if Odysseus is down
    res.json({
      response: `I'm having trouble reaching the AI server right now. Please try again in a moment, or check that Odysseus is running on ${ODYSSEUS_URL}.`,
      model: 'offline',
    });
  }
});

// Streaming chat — SSE for real-time responses
app.post('/api/chat/stream', async (req, res) => {
  try {
    const { message, userId, model, temperature } = req.body;
    trackAPIUsage('/api/chat/stream', userId);

    const response = await axios.post(
      `${ODYSSEUS_URL}/v1/chat/completions`,
      {
        model: model || DEFAULT_MODEL,
        messages: [{ role: 'user', content: message }],
        stream: true,
        temperature: temperature ?? 0.7,
      },
      { timeout: 120_000, responseType: 'stream' }
    );

    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('X-Accel-Buffering', 'no');

    response.data.on('data', (chunk) => {
      const lines = chunk.toString().split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            res.write('data: [DONE]\n\n');
          } else {
            res.write(`data: ${data}\n\n`);
          }
        }
      }
    });

    response.data.on('end', () => {
      res.end();
    });

    response.data.on('error', (err) => {
      console.error('[STREAM ERROR]', err.message);
      res.end();
    });

  } catch (error) {
    console.error('[ODYSSEUS STREAM ERROR]', error.message);
    res.status(500).json({ error: 'Stream failed — is Odysseus running?' });
  }
});

// List available models (from Odysseus /v1/models)
app.get('/api/models', async (req, res) => {
  try {
    const response = await axios.get(`${ODYSSEUS_URL}/v1/models`, { timeout: 10_000 });
    res.json(response.data);
  } catch (error) {
    // Return default model list as fallback
    res.json({
      object: 'list',
      data: [{ id: DEFAULT_MODEL, object: 'model', created: Date.now(), owned_by: 'local' }],
    });
  }
});

// Smart Home control via chat (Odysseus routes this internally)
// Body: { message: "turn on the living room lights" }
app.post('/api/home/chat', async (req, res) => {
  try {
    const { message, userId } = req.body;
    trackAPIUsage('/api/home/chat', userId);

    const data = await ollamaChat(
      [
        {
          role: 'system',
          content: 'You control the smart home. Respond briefly. Available actions: call /api/home/ha/services, /api/home/scene/{name}, /api/home/shell.',
        },
        { role: 'user', content: message },
      ],
      { model: DEFAULT_MODEL }
    );

    const response = data.choices?.[0]?.message?.content || 'OK';
    res.json({ response });
  } catch (error) {
    console.error('[HOME CHAT ERROR]', error.message);
    res.status(500).json({ error: error.message });
  }
});

// =============================================================================
// OLLAMA - Image Generation (Placeholder)
// =============================================================================

app.post('/api/image-generate', async (req, res) => {
  try {
    const { prompt, userId } = req.body;
    
    trackAPIUsage('/api/image-generate', userId);

    // In production, this would call Stable Diffusion or similar
    // For now, return a placeholder image
    const imageUrl = `https://picsum.photos/512/512?random=${Date.now()}`;
    
    console.log(`[IMAGE] Generate request - User: ${userId} - Prompt: ${prompt}`);
    res.json({ 
      imageUrl: imageUrl,
      prompt: prompt
    });

  } catch (error) {
    console.error('[IMAGE ERROR]', error.message);
    res.status(500).json({ error: error.message });
  }
});

// =============================================================================
// OLLAMA - Music Generation (Placeholder)
// =============================================================================

app.post('/api/music-generate', async (req, res) => {
  try {
    const { prompt, userId } = req.body;
    
    trackAPIUsage('/api/music-generate', userId);

    // In production, this would call Suno API or similar
    console.log(`[MUSIC] Generate request - User: ${userId} - Prompt: ${prompt}`);
    res.json({ 
      audioUrl: `data:audio/mp3;base64,placeholder_${Date.now()}`,
      prompt: prompt
    });

  } catch (error) {
    console.error('[MUSIC ERROR]', error.message);
    res.status(500).json({ error: error.message });
  }
});

// =============================================================================
// STRIPE - Get Prices (Dynamic from Dashboard)
// =============================================================================

app.get('/api/prices', async (req, res) => {
  try {
    const prices = await stripe.products.list({
      active: true,
      limit: 10
    });

    const formattedPrices = prices.data.map(product => ({
      id: product.id,
      name: product.name,
      prices: product.default_price ? [{
        id: product.default_price.id,
        unit_amount: product.default_price.unit_amount / 100,
        currency: product.default_price.currency,
        type: product.default_price.type,
        interval: product.default_price.recurring?.interval
      }] : []
    }));

    res.json({ products: formattedPrices });

  } catch (error) {
    console.error('[STRIPE PRICES ERROR]', error.message);
    res.status(500).json({ error: error.message });
  }
});

// =============================================================================
// HEALTH CHECK
// =============================================================================

app.get('/api/health', (req, res) => {
  res.json({ 
    status: 'healthy',
    version: '1.0.0',
    timestamp: new Date().toISOString()
  });
});

// =============================================================================
// SERVER START
// =============================================================================

app.listen(PORT, () => {
  console.log(`
╔════════════════════════════════════════════════════════════╗
║              BYRDHOUSE BACKEND v2.0                       ║
╠════════════════════════════════════════════════════════════╣
║  Status: RUNNING                                          ║
║  Port: ${PORT}                                              ║
║  Stripe: ${process.env.STRIPE_SECRET_KEY ? '✓ Configured' : '✗ Missing'}                        ║
║  AI Backend: ${ODYSSEUS_URL}              ║
║  AI Model: ${DEFAULT_MODEL}                                  ║
║  Smart Home: ${HOME_ASSISTANT_URL || '(not configured)'}  ║
╚════════════════════════════════════════════════════════════╝
  `);
});

module.exports = app;