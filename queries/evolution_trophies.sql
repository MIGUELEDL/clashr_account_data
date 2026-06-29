SELECT 
    ingestion_date,
    COUNT(DISTINCT player_tag) as unique_players,
    ROUND(AVG(trophies), 0) as avg_trophies,
    ROUND(MAX(trophies), 0) as max_trophies
FROM clashr_account_data.profile_silver
GROUP BY ingestion_date
ORDER BY ingestion_date DESC