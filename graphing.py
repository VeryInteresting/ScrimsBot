import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os

def create_performance_graph(seasons, kds):
    """Creates a line chart of a player's K/D ratio over seasons."""
    if not os.path.exists('charts'):
        os.makedirs('charts')

    plt.figure(figsize=(10, 5))
    plt.plot(seasons, kds, marker='o', linestyle='-', color='b')
    plt.title('Player K/D Ratio Over Seasons')
    plt.xlabel('Season')
    plt.ylabel('K/D Ratio')
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()

    chart_path = 'charts/performance_graph.png'
    plt.savefig(chart_path)
    plt.close()
    return chart_path