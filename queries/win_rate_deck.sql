-- Win Rate por Deck
SELECT 
    deck_hash,
    COUNT(*) as total_battles,
    SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
    ROUND(
        SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 
        2
    ) as win_rate_pct,
    ROUND(AVG(player_elixir_avg), 2) as avg_elixir
FROM clashr_account_data.fact_battles
WHERE battle_type IN ('Ladder', 'PvP')
GROUP BY deck_hash
HAVING COUNT(*) >= 5
ORDER BY win_rate_pct DESC
LIMIT 20