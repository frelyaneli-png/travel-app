    <script>
        (function() {
            var teamKey = 'travel_recent_teams';
            var identityKey = 'travel_identity_{{ team_id }}';
            var teamName = "{{ team_name }}";
            
            // 记忆团队 - 确保存入
            try {
                var teams = JSON.parse(localStorage.getItem(teamKey) || '[]');
                teams = teams.filter(function(t) { return t !== teamName; });
                teams.unshift(teamName);
                if (teams.length > 5) teams = teams.slice(0, 5);
                localStorage.setItem(teamKey, JSON.stringify(teams));
            } catch(e) {
                console.log('保存团队失败:', e);
            }
            
            // 身份选择
            var select = document.getElementById('identitySelect');
            if (select) {
                select.addEventListener('change', function() {
                    localStorage.setItem(identityKey, this.value);
                });
                var saved = localStorage.getItem(identityKey);
                if (saved) {
                    select.value = saved;
                }
            }
        })();
    </script>
