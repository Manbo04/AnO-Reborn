# Bot Nations System Documentation

## Overview

The **Bot Nations System** provides autonomous trading bots that automatically buy, sell, and produce resources to stabilize the game market economy. This prevents extreme price volatility and ensures a healthy trading environment for all players.

## Features

- **Automatic Market Stabilization**: Bots buy low and sell high to smooth price fluctuations
- **Resource Production**: Bots generate resources to maintain supply
- **Price Targeting**: Each resource has a target price range maintained by bots
- **Reserve Management**: Bots maintain minimum reserve levels to ensure availability
- **Admin Control**: Full API and CLI for manual intervention

## Bot Nations

### 1. Market Stabilizer (ID: 9999)
- **Primary Role**: Stabilize market prices
- **Strategy**:
  - Buys resources when prices fall below minimum target
  - Sells resources when prices rise above maximum target
  - Maintains large reserves to influence market
- **Run Frequency**: Every 2 hours (automated)

### 2. Resource Producer (ID: 9998)
- **Primary Role**: Produce and supply resources
- **Strategy**:
  - Generates base resources daily
  - Maintains minimum reserve thresholds
  - Serves as a fallback supply when player production is low
- **Run Frequency**: Every 2 hours (automated)

## Target Prices

Each resource has a target price range that bots work to maintain:

```
Rations:     100-150 gold/unit   (target: 125)
Lumber:       80-120 gold/unit   (target: 100)
Steel:      200-300 gold/unit   (target: 250)
Aluminium:  150-250 gold/unit   (target: 200)
```

## Minimum Reserves

Bots maintain minimum reserve levels to ensure availability:

```
Rations:     100,000 units
Lumber:      100,000 units
Steel:        50,000 units
Aluminium:    50,000 units
```

## Usage

### CLI Management

Initialize bots:
```bash
python bot_cli.py init
```

Check bot status:
```bash
python bot_cli.py status                    # Check all bots
python bot_cli.py status market_stabilizer  # Check specific bot
```

Run market stabilization:
```bash
python bot_cli.py stabilize
```

Run resource production:
```bash
python bot_cli.py produce
```

Cancel all bot orders:
```bash
python bot_cli.py cancel-orders
```

View configuration:
```bash
python bot_cli.py config
```

### API Endpoints (Admin Only)

**Get all bot statuses:**
```
GET /admin/bots/status
```

Response:
```json
{
  "success": true,
  "bots": {
    "market_stabilizer": {
      "bot_id": 9999,
      "gold": 10000000,
      "resources": {
        "rations": 1000000,
        "lumber": 1000000,
        "steel": 500000,
        "aluminium": 500000
      },
      "current_prices": {...},
      "active_offers": [...]
    },
    ...
  }
}
```

**Trigger market stabilization:**
```
POST /admin/bots/stabilize
Body: {"bot_id": 9999}
```

**Trigger resource production:**
```
POST /admin/bots/produce
Body: {"bot_id": 9998}
```

**Cancel all orders for a bot:**
```
POST /admin/bots/cancel-orders
Body: {"bot_id": 9999}
```

**Get bot configuration:**
```
GET /admin/bots/config
```

**Initialize bots:**
```
POST /admin/bots/init
```

## Automated Tasks (Celery)

The system includes automatic Celery tasks:

1. **Market Stabilization** (every 2 hours)
   - Executes `execute_market_stabilization()`
   - Executes `produce_resources()`
   - Updates active market orders

2. **Cancel Stale Orders** (every 6 hours)
   - Clears old bot orders
   - Refreshes trading strategy

3. **Check Bot Status** (every 1 hour)
   - Logs bot status for monitoring
   - Helps identify issues

To enable in Celery Beat schedule:
```python
'bot-market-stabilization': {
    'task': 'tasks.task_bot_market_stabilization',
    'schedule': crontab(minute=0, hour='*/2'),  # Every 2 hours
},
'bot-cancel-orders': {
    'task': 'tasks.task_bot_cancel_stale_orders',
    'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
},
'bot-status-check': {
    'task': 'tasks.task_bot_check_status',
    'schedule': crontab(minute=0, hour='*'),  # Every hour
},
```

## How It Works

### Market Stabilization Algorithm

```
For each resource:
  1. Get current market price
  2. If price < minimum target AND bot has reserve budget:
     - Buy amount to reach minimum reserve level
     - Place buy order at current price
  3. If price > maximum target AND bot has surplus:
     - Sell surplus above minimum reserve
     - Place sell order at current price
```

### Resource Production

Daily production amounts:
```
Rations:     50,000 units/day
Lumber:      40,000 units/day
Steel:       20,000 units/day
Aluminium:   15,000 units/day
```

These amounts can be adjusted in `bot_nations.py:produce_resources()`.

## Configuration

Edit target prices and minimum reserves in `bot_nations.py`:

```python
TARGET_PRICES = {
    "rations": {"min": 100, "max": 150, "target": 125},
    "lumber": {"min": 80, "max": 120, "target": 100},
    "steel": {"min": 200, "max": 300, "target": 250},
    "aluminium": {"min": 150, "max": 250, "target": 200},
}

MIN_RESERVES = {
    "rations": 100000,
    "lumber": 100000,
    "steel": 50000,
    "aluminium": 50000,
}
```

## Monitoring

Bot status includes:
- Current gold balance
- Resource amounts and comparison to minimum reserves
- Active market offers
- Current market prices vs. targets

Check logs for detailed information:
```bash
tail -f errors.log | grep "market stabilization"
```

## Troubleshooting

### Bot nations not created
```bash
python bot_cli.py init
```

### Market not stabilizing
1. Check bot resources: `python bot_cli.py status`
2. Check gold balance
3. Cancel stale orders: `python bot_cli.py cancel-orders`
4. Run stabilization manually: `python bot_cli.py stabilize`

### Price targets not being met
1. Increase bot reserves or starting gold
2. Adjust target price ranges
3. Increase production amounts
4. Verify bot orders are being placed: `python bot_cli.py status`

## Database Schema

Bot nations use standard user accounts with special IDs:

```sql
-- Bot user account (in users table)
INSERT INTO users (id, username, auth_type)
VALUES (9999, 'BOT_MARKET_STABILIZER', 'bot');

-- Bot statistics (in stats table)
INSERT INTO stats (id, gold)
VALUES (9999, 10000000);

-- Bot resources (in resources table)
INSERT INTO resources (id, rations, lumber, steel, aluminium)
VALUES (9999, 1000000, 1000000, 500000, 500000);
```

## Performance Considerations

- Bot market operations are non-blocking
- Uses bulk database operations for efficiency
- Caches price calculations
- Limits to 20 active orders per bot at a time
- Database indexes on `offers(user_id)` and `offers(type)` recommended

## Security Notes

- Bot accounts are system accounts, not player accounts
- Bot operations are logged for audit purposes
- Admin API endpoints should be protected with proper authentication
- Bot gold and resources don't appear in player leaderboards
- Bot nation IDs are reserved and cannot be assigned to players

## Future Enhancements

- [ ] Dynamic price target adjustment based on supply/demand
- [ ] Machine learning for price prediction
- [ ] Multiple stabilization strategies (aggression levels)
- [ ] Per-resource production balance
- [ ] Market intervention logging and reporting
- [ ] Bot performance metrics and analytics
- [ ] Emergency shutdown procedures
