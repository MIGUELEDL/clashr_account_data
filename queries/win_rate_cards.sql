-- Win Rate por Carta (CORRIGIDO)
SELECT 
    card_name,
    COUNT(DISTINCT bs.battle_id) as battles_with_card,
    SUM(CASE WHEN bs.result = 'win' THEN 1 ELSE 0 END) as wins_with_card,
    ROUND(
        SUM(CASE WHEN bs.result = 'win' THEN 1 ELSE 0 END) * 100.0 / 
        COUNT(DISTINCT bs.battle_id),
        2
    ) as win_rate_pct
FROM clashr_account_data.battles_silver bs
CROSS JOIN UNNEST(bs.player_deck) AS t(card_name)
WHERE bs.battle_type IN ('Ladder', 'PvP')
GROUP BY card_name
HAVING COUNT(DISTINCT bs.battle_id) >= 5
ORDER BY win_rate_pct DESC
LIMIT 15