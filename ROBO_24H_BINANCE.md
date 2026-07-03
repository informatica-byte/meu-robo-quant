# Robô Binance 24h

Este worker roda separado do Streamlit. O Streamlit é painel; este arquivo é o motor que pode ficar 24h em um VPS, Render, Railway ou computador ligado.

## Segurança padrão

Por padrão, rode primeiro em paper trading. Nesse modo ele não precisa de chave da Binance, não envia ordem nenhuma e grava as operações simuladas:

```env
BOT_MODE=paper
BOT_PAPER_INITIAL_CASH=10000
```

Depois de alguns dias, você pode testar a assinatura da Binance em testnet:

```env
BOT_MODE=binance
BINANCE_USE_TESTNET=true
BINANCE_TEST_ORDER=true
BINANCE_REAL_TRADING_ENABLED=false
```

Para operar real, você precisa mudar conscientemente e aceitar o risco:

```env
BOT_MODE=binance
BINANCE_USE_TESTNET=false
BINANCE_TEST_ORDER=false
BINANCE_REAL_TRADING_ENABLED=true
```

## Variáveis principais

```env
BINANCE_API_KEY=sua_chave
BINANCE_API_SECRET=seu_segredo
BOT_MODE=paper
BOT_PAPER_INITIAL_CASH=10000
BOT_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
BOT_USDT_PER_TRADE=25
BOT_MAX_POSITIONS=3
BOT_STOP_LOSS_PCT=5
BOT_TAKE_PROFIT_PCT=10
BOT_DAILY_LOSS_LIMIT_PCT=3
BOT_INTERVAL_SECONDS=300
BUY_SCORE=74
SELL_SCORE=36
```

## Rodar

```powershell
python outputs\crypto_bot_worker.py
```

## Rodar grátis no GitHub Actions

Para custo zero, use o modo agendado do GitHub Actions. Ele não fica em loop infinito; ele acorda, roda um ciclo, salva estado e dorme de novo.

Crie este arquivo no repositório:

```text
.github/workflows/robo-paper.yml
```

Use o conteúdo de `robo-paper-github-actions.yml`.

O workflow roda a cada 15 minutos e também pode ser disparado manualmente em `Actions > Robo Paper 24h > Run workflow`.

O robô grava:

- `bot_state.json`: posições acompanhadas pelo robô.
- `bot_trades.csv`: histórico de compras e vendas.

Sequência recomendada:

1. `BOT_MODE=paper` por vários dias.
2. `BOT_MODE=binance` com `BINANCE_USE_TESTNET=true`.
3. Só depois considerar dinheiro real, com valores pequenos e trava diária.
