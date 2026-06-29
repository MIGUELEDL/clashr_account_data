SELECT 
    CASE WHEN result = 'win' THEN 'Winner' ELSE 'Loser' END as outcome,
    COUNT(*) as total_battles,
    ROUND(AVG(player_elixir_avg), 3) as avg_elixir,
    ROUND(STDDEV(player_elixir_avg), 3) as stddev_elixir
FROM clashr_account_data.battles_silver
WHERE battle_type = 'PvP'
GROUP BY result
ORDER BY result DESC;