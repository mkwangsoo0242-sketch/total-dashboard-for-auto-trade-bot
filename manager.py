import time
from rich.console import Console
from rich.table import Table
from rich.live import Live
from bots.trading_bot import TradingBot

class BotManager:
    def __init__(self):
        self.bots = {
            "5m": TradingBot("Bot_5m", "5m"),
            "15m": TradingBot("Bot_15m", "15m"),
            "30m": TradingBot("Bot_30m", "30m"),
            "1h": TradingBot("Bot_1h", "1h")
        }
        self.console = Console()

    def start_all(self):
        self.console.print("[bold green]모든 봇을 시작합니다...[/bold green]")
        for bot in self.bots.values():
            bot.start()

    def stop_all(self):
        self.console.print("[bold red]모든 봇을 정지합니다...[/bold red]")
        for bot in self.bots.values():
            bot.stop()

    def display_dashboard(self):
        with Live(self._generate_table(), refresh_per_second=1) as live:
            try:
                while True:
                    time.sleep(1)
                    live.update(self._generate_table())
            except KeyboardInterrupt:
                self.stop_all()

    def _generate_table(self) -> Table:
        table = Table(title="봇 통합 관리 시스템")
        table.add_column("봇 이름", style="cyan")
        table.add_column("인터벌", style="magenta")
        table.add_column("상태", style="green")
        table.add_column("마지막 실행 시간", style="yellow")
        
        for bot in self.bots.values():
            status_style = "green" if bot.status == "Running" else "red"
            last_run_str = bot.last_run.strftime("%H:%M:%S") if bot.last_run else "-"
            table.add_row(
                bot.name, 
                bot.interval, 
                f"[{status_style}]{bot.status}[/{status_style}]", 
                last_run_str
            )
            
        return table
