"""MCP Resources: static documentation exposed as resources for LLM context."""

from mcp.server.fastmcp import FastMCP


def register_resources(mcp: FastMCP) -> None:
    """Register documentation resources on the given MCP server instance."""

    @mcp.resource("tron://event-types")
    def get_event_types() -> str:
        """
        TRON event type quick reference.
        Describes the business meaning, trigger timing, and key fields
        of all 7 event types.
        Loaded as static context automatically; does not consume a tool call.
        """
        return """\
# TRON Event Types

## 7 Event Types Reference

| triggerName | collection | Trigger Timing | Unique Key Field |
|---|---|---|---|
| blockTrigger | block | Every new block produced | blockNumber |
| transactionTrigger | transaction | Transaction packaged into a block | transactionId |
| contractEventTrigger | contractevent | Contract emits an event (ABI-decoded) | uniqueId |
| contractLogTrigger | contractlog | Contract LOG operation (raw hex) | uniqueId |
| solidityTrigger | solidity | Block is finalized (solidified) | latestSolidifiedBlockNumber |
| solidityEventTrigger | solidityevent | Solidified contract event | uniqueId |
| solidityLogTrigger | soliditylog | Solidified contract raw log | uniqueId |

## Important Differences

### contractevent vs contractlog
- **contractevent**: ABI-decoded; topicMap/dataMap contain readable key-value pairs.
  Prefer this collection for event analysis.
- **contractlog**: Raw logs; topicList is a hex string array that requires
  additional decoding to interpret.

### block/transaction vs solidityevent/soliditylog
- **block/transaction/contractevent/contractlog**: Real-time data, written as soon
  as the block is produced. There is a very small chance of chain rollback.
- **solidityevent/soliditylog**: Finalized data, confirmed by enough subsequent
  blocks. Will not be rolled back. Best for deterministic statistics and analysis.

## Timestamp Field
All collections use a `timeStamp` field with **millisecond Unix timestamps** (long type).
Time range query example:
- 2024-01-15 00:00:00 UTC = 1705276800000
- Query a single day: { "timeStamp": { "$gte": 1705276800000, "$lt": 1705363200000 } }

## Address Format
TRON addresses are Base58Check-encoded, starting with **T**, 34 characters long.
Example: TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t (USDT contract address)

## The removed Field
In contractevent, removed=true indicates the event was rolled back; the MongoDB
plugin deletes the corresponding document.
In solidityevent, removed=true never appears (solidified data is never rolled back).
"""

    @mcp.resource("tron://query-guide")
    def get_query_guide() -> str:
        """
        MCP tool usage guide describing recommended scenarios and calling order.
        """
        return """\
# TRON Event MCP Tool Usage Guide

## Recommended Workflow

### Step 1: Understand the Data
1. Call `describe_schema()` to learn the field structure of all collections.
2. Call `get_collection_stats()` to check data scale and time coverage.

### Step 2: Choose the Right Tool

| Scenario | Recommended Tool |
|---|---|
| Quick look at latest events | `get_recent_events` |
| Query by block height | `get_block` |
| Query by transaction hash | `get_transaction` |
| Query a contract's activity | `search_contract_activity` |
| Find most active contracts | `get_top_contracts` |
| Analyze event count trends | `aggregate_by_time` |
| Analyze tx success rate / energy | `get_transaction_stats` |
| Complex custom queries | `query_events` |

## Performance Tips
- Narrow down the time range to avoid full-collection scans.
- Use the `fields` parameter to return only needed fields, reducing data transfer.
- For large-scale analysis, prefer aggregation tools (get_top_contracts,
  aggregate_by_time) over fetching raw data and computing on the LLM side.

## Query Limits
- Maximum 500 documents per request (use skip for pagination).
- Single query timeout: 10 seconds.
- $where, $function and other JavaScript operators are forbidden.
"""

    @mcp.resource("tron://known-contracts")
    def get_known_contracts() -> str:
        """
        Well-known TRON contract addresses and their metadata.
        Helps the LLM resolve natural-language references like "USDT" or "SunSwap"
        to actual on-chain addresses without asking the user.
        """
        return """\
# Well-Known TRON Contracts

## Stablecoins
| Name | Symbol | Contract Address | Decimals | Event to Watch |
|------|--------|-----------------|----------|----------------|
| Tether USD | USDT (TRC20) | TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t | 6 | Transfer(address,address,uint256) |
| USD Coin | USDC (TRC20) | TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8 | 6 | Transfer(address,address,uint256) |
| Decentralized USD | USDD | TPYmHEhy5n8TCEfYGqW2rPxsghSfzghPDn | 18 | Transfer(address,address,uint256) |
| TrueUSD | TUSD | TUpMhErZL2fhh4sVNULAbNKLokS4GjC1F4 | 18 | Transfer(address,address,uint256) |

## DeFi Protocols — SunSwap

### SunSwap V1
| Name | Contract Address | Description |
|------|-----------------|-------------|
| V1 Factory | TXk8rQSAvPvBBNtqSoY6nCfsXWCSSpTVQF | Creates V1 exchange contracts (one per token) |

### SunSwap V2
| Name | Contract Address | Description |
|------|-----------------|-------------|
| V2 Router (current) | TXF1xDbVGdxFGbovmmmXvBGu8ZiE3Lq4mR | DEX router for token swaps |
| V2 Router (deprecated) | TKzxdSv2FZKQrEqkKVgp5DcwEXBEKMg2Ax | Legacy router, still seen in historical data |
| V2 Factory | TKWJdrQkqHisa1X8HUdHEfREvTzw4pMAaY | Factory that creates trading pair contracts |

### SunSwap V3
| Name | Contract Address | Description |
|------|-----------------|-------------|
| V3 Factory | TThJt8zaJzJMhCEScH7zWKnp5buVZqys9x | Creates V3 concentrated-liquidity pools |
| V3 Router | TQAvWQpT9H916GckwWDJNhYZvQMkuRL7PN | Swap router for V3 pools |
| NFT Position Manager | TLSWrv7eC1AZCXkRjpqMZUmvgd99cj7pPF | Manages V3 LP positions as NFTs |

### SunSwap Smart Router & Governance
| Name | Contract Address | Description |
|------|-----------------|-------------|
| Smart Router | TCFNp179Lg46D16zKoumd4Poa2WFFdtqYj | Aggregates V1/V2/V3 for optimal routing |
| sun.io | TKkeiboTkxXKJpbmVFbv4a8ov5rAfRDMf9 | Governance and yield aggregator |

## DeFi Protocols — JustLend DAO

### Infrastructure
| Name | Contract Address | Description |
|------|-----------------|-------------|
| Unitroller | TGjYzgCyPobsNS9n6WcbdLVR9dH7mWqFx7 | Management / proxy entry point |
| Comptroller | TB23wYojvAsSx6gR8ebHiBqwSeABiBMPAr | Risk management (collateral factor, liquidation) |
| PriceOracle | TMiNCmvD3zdsv6mk7niBU6NPBzVNjYMQTV | Price feed |
| PriceOracleProxy | TCKp2AzuhzV4B4Ahx1ej4mvQgHZ1kH7F7k | Oracle proxy |
| GovernorBravo | TEqiF5JbhDPD77yjEfnEMncGRZNDt2uogD | Governance |
| Timelock | TRWNvb15NmfNKNLhQpxefFz7cNjrYjEw7x | Governance timelock |
| sTRX Token | TU3kjFuhtEo42tsCBtfYUAZxoqQ4yuSLQ5 | Staked TRX |
| EnergyRental | TU2MJ5Veik1LRAgjeSzEdvmDYx7mefJZvd | Energy rental service |

### jToken Addresses (CErc20Delegator)
Each jToken represents a supply/borrow market in JustLend.
When users supply assets they receive jTokens; when they borrow, the jToken contract emits events.

| Token | jToken Address |
|-------|---------------|
| TRX | TE2RzoSV3wFK99w6J9UnnZ4vLfXYoxvRwP |
| USDT | TXJgMdjVX5dKiQaUi9QobwNxtSQaFqccvd |
| USDD | TKFRELGGoRgiayhwJTNNLqCNjFoLBh3Mnf |
| USDC | TNSBA6KvSvMoTqQcEgpVK7VhHT3z7wifxy |
| TUSD | TSXv71Fy5XdL3Rh2QfBoUu3NAaM4sMif8R |
| BTC | TLeEu311Cbw63BcmMHDgDLu7fnk9fqGcqT |
| ETH | TR7BUFRQeq1w5jAZf1FKx85SHuX6PfMqsV |
| ETHB | TWBxQMb6RD3qmkXUXpNwVCYbL8SHNreru6 |
| WBTC | TVyvpmaVmz25z2GaXBDDjzLZi5iR5dBzGd |
| SUN | TPXDpkg9e3eZzxqxAUyke9S4z4pGJBJw9e |
| JST | TWQhCXaWz4eHK4Kd1ErSDHjMFPoPc9czts |
| WIN | TRg6MnpsFXc82ymUPgf5qbj59ibxiEDWvv |
| BTT | TUaUHU9Dy8x5yNi1pKnFYqHWojot61Jfto |
| NFT | TFpPyDCKvNFgos3g3WVsAqMrdqhB81JXHE |
| USDJ | TL5x9MtSnDy537FXKx53yAaHRRNdg9TkkA |
| wstUSDT | TD5SdLw5scR6mXgyMK2xKrFJpauDjpKqrW |
| sTRX | TJQ9rbVe9ei3nNtyGgBL22Fuu2xYjZaLAQ |
| USD1 | TBEKggwqFkrc4KckQVR9BLucAmQugafEZf |
| WBTT | TUY54PVeH6WCcYCd6ZXXoBDsHytN9V5PXt |

## Infrastructure
| Name | Contract Address | Description |
|------|-----------------|-------------|
| WTRX | TNUC9Qb1rRpS5CbWLmNMxXBjyFoydXjWFR | Wrapped TRX (TRC20) |

## Common Event Signatures

### ERC20 / TRC20
| Event | Signature | Meaning |
|-------|-----------|---------|
| Transfer | Transfer(address,address,uint256) | Token transfer: from, to, amount |
| Approval | Approval(address,address,uint256) | Spending authorization: owner, spender, amount |

### SunSwap V1 (Exchange contracts)
| Event | Signature | Meaning |
|-------|-----------|---------|
| TokenPurchase | TokenPurchase(address,uint256,uint256) | TRX → Token swap (buyer, trx_sold, tokens_bought) |
| TrxPurchase | TrxPurchase(address,uint256,uint256) | Token → TRX swap (buyer, tokens_sold, trx_bought) |
| AddLiquidity | AddLiquidity(address,uint256,uint256) | Add liquidity (provider, trx_amount, token_amount) |
| RemoveLiquidity | RemoveLiquidity(address,uint256,uint256) | Remove liquidity (provider, trx_amount, token_amount) |
| Snapshot | Snapshot(address,uint256) | Price snapshot (operator, trx_balance) |

### SunSwap V2 (Pair contracts)
| Event | Signature | Meaning |
|-------|-----------|---------|
| Swap | Swap(address,uint256,uint256,uint256,uint256,address) | DEX swap |
| Sync | Sync(uint112,uint112) | Liquidity pool reserve update |
| Mint | Mint(address,uint256,uint256) | Liquidity added to pool |
| Burn | Burn(address,uint256,uint256,address) | Liquidity removed from pool |

### SunSwap V3 (Pool contracts)
| Event | Signature | Meaning |
|-------|-----------|---------|
| Swap | Swap(address,address,int256,int256,uint160,uint128,int24) | V3 swap (sender, recipient, amount0, amount1, sqrtPriceX96, liquidity, tick) |
| IncreaseLiquidity | IncreaseLiquidity(uint256,uint128,uint256,uint256) | Add concentrated liquidity (tokenId, liquidity, amount0, amount1) |
| DecreaseLiquidity | DecreaseLiquidity(uint256,uint128,uint256,uint256) | Remove concentrated liquidity (tokenId, liquidity, amount0, amount1) |
| Collect | Collect(uint256,address,uint256,uint256) | Collect fees (tokenId, recipient, amount0, amount1) |

### JustLend DAO (emitted by jToken contracts)
| Event | Signature | Meaning |
|-------|-----------|---------|
| Mint | Mint(address,uint256,uint256) | User supplies assets, receives jTokens (minter, mintAmount, mintTokens) |
| Redeem | Redeem(address,uint256,uint256) | User redeems jTokens for underlying (redeemer, redeemAmount, redeemTokens) |
| Borrow | Borrow(address,uint256,uint256,uint256,uint256) | User borrows assets (borrower, borrowAmount, accountBorrows, totalBorrows, borrowIndex) |
| RepayBorrow | RepayBorrow(address,address,uint256,uint256,uint256,uint256) | User repays borrow (payer, borrower, repayAmount, accountBorrows, totalBorrows, borrowIndex) |
| LiquidateBorrow | LiquidateBorrow(address,address,uint256,address,uint256) | Liquidation (liquidator, borrower, repayAmount, cTokenCollateral, seizeTokens) |

## Tips
- When the user says "USDT transfers", query contractevent with:
  contractAddress = TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t, eventName = "Transfer"
- The `dataMap.value` or `topicMap.value` field contains the raw amount;
  divide by 10^decimals to get the human-readable value
  (e.g. USDT raw 1000000 = 1.0 USDT)
- SunSwap pair contracts are NOT listed here because they are dynamically
  created; use get_top_contracts to discover active pairs
- For JustLend analysis, query contractevent with jToken address as contractAddress
  and event name like "Mint", "Borrow", "Redeem", "LiquidateBorrow", etc.
- JustLend Mint/Redeem events have the same name as SunSwap Mint events but
  different parameter structures; distinguish by contractAddress
"""
