WITH ranked_battles AS (
    SELECT 
        player_tag,
        battle_time,
        result,
        ROW_NUMBER() OVER (PARTITION BY player_tag ORDER BY battle_time) as rn,
        LAG(result) OVER (PARTITION BY player_tag ORDER BY battle_time) as prev_result
    FROM clashr_account_data.fact_battles
),
streak_groups AS (
    SELECT 
        player_tag,
        result,
        SUM(CASE WHEN result = prev_result OR prev_result IS NULL THEN 0 ELSE 1 END) 
            OVER (PARTITION BY player_tag ORDER BY rn) as streak_group
    FROM ranked_battles
),
streaks AS (
    SELECT 
        player_tag,
        result,
        COUNT(*) as streak_length
    FROM streak_groups
    GROUP BY player_tag, result, streak_group
)
SELECT 
    player_tag,
    result as streak_type,
    MAX(streak_length) as longest_streak,
    COUNT(*) as num_streaks
FROM streaks
GROUP BY player_tag, result
ORDER BY MAX(streak_length) DESC
LIMIT 20