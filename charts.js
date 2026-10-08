fetch('/api/chart-data')
    .then(response => response.json())
    .then(data => {
        // Horizontal Bar Chart: Category
        new Chart(document.getElementById('categoryChart'), {
            type: 'bar',
            data: {
                labels: Object.keys(data.categories),
                datasets: [{
                    label: 'Complaints',
                    data: Object.values(data.categories),
                    backgroundColor: '#38bdf8'
                }]
            },
            options: {
                indexAxis: 'y',
                plugins: { legend: { display: false } }
            }
        });

        // Pie Chart: Status Distribution
        new Chart(document.getElementById('statusChart'), {
            type: 'pie',
            data: {
                labels: Object.keys(data.statuses),
                datasets: [{
                    data: Object.values(data.statuses),
                    backgroundColor: ['#f87171', '#fbbf24', '#34d399']
                }]
            }
        });
    });