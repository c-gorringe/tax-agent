"""CLI for Tax Agent - Shopify Sales Tax Filing Tool."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import extract, transform, aggregate, reconcile, nexus, render

# Load environment variables
load_dotenv()

app = typer.Typer(help="Shopify Sales Tax Filing Agent")
console = Console()


def get_period_dates(period: str, year: int, month: Optional[int] = None, quarter: Optional[int] = None) -> tuple:
    """Calculate start and end dates for a period."""
    if period == "monthly":
        if month is None:
            raise ValueError("Month is required for monthly period")
        if not 1 <= month <= 12:
            raise ValueError("Month must be 1-12")
        start = datetime(year, month, 1)
        # Last day of month
        if month == 12:
            end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = datetime(year, month + 1, 1) - timedelta(days=1)
        period_name = f"{year}-{month:02d}"
    elif period == "quarterly":
        if quarter is None:
            raise ValueError("Quarter is required for quarterly period")
        if not 1 <= quarter <= 4:
            raise ValueError("Quarter must be 1-4")
        start_month = (quarter - 1) * 3 + 1
        start = datetime(year, start_month, 1)
        end_month = quarter * 3
        if end_month == 12:
            end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = datetime(year, end_month + 1, 1) - timedelta(days=1)
        period_name = f"{year}-Q{quarter}"
    else:
        raise ValueError(f"Unknown period type: {period}")
    
    # Set times to cover full days
    start = start.replace(hour=0, minute=0, second=0)
    end = end.replace(hour=23, minute=59, second=59)
    
    return start, end, period_name


@app.command()
def run(
    period: str = typer.Option("monthly", help="Period type: monthly or quarterly"),
    year: int = typer.Option(..., help="Year (e.g., 2026)"),
    month: Optional[int] = typer.Option(None, help="Month (1-12) for monthly period"),
    quarter: Optional[int] = typer.Option(None, help="Quarter (1-4) for quarterly period"),
    skip_extract: bool = typer.Option(False, help="Skip extraction, use existing raw data"),
    config_dir: str = typer.Option("config", help="Configuration directory"),
    data_dir: str = typer.Option("data", help="Data directory"),
):
    """Run the full tax filing workflow for a period."""
    console.print(f"[bold blue]Tax Agent - {period.title()} Filing Run[/bold blue]")
    console.print()
    
    # Calculate period dates
    try:
        start_date, end_date, period_name = get_period_dates(period, year, month, quarter)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    
    console.print(f"Period: {period_name}")
    console.print(f"Date range: {start_date.date()} to {end_date.date()}")
    console.print()
    
    # Load configurations
    stores_config = extract.load_stores_config(f"{config_dir}/stores.yaml")
    
    # Step 1: Extract
    if not skip_extract:
        console.print("[bold]Step 1: Extracting orders from Shopify...[/bold]")
        try:
            raw_orders = extract.extract_period(
                stores_config,
                start_date,
                end_date,
                data_dir=f"{data_dir}/raw",
                period_name=period_name
            )
        except Exception as e:
            console.print(f"[red]Extraction failed: {e}[/red]")
            raise typer.Exit(1)
    else:
        console.print("[bold]Step 1: Loading existing raw data...[/bold]")
        raw_orders = {}
        for store_id in stores_config.get("stores", {}).keys():
            try:
                raw_orders[store_id] = extract.load_raw_orders(
                    store_id, period_name, data_dir=f"{data_dir}/raw"
                )
                console.print(f"  Loaded {len(raw_orders[store_id])} orders from {store_id}")
            except FileNotFoundError:
                console.print(f"[yellow]  No raw data found for {store_id}[/yellow]")
    
    console.print()
    
    # Step 2: Transform
    console.print("[bold]Step 2: Transforming orders...[/bold]")
    all_orders = []
    all_refunds = []
    
    for store_id, orders in raw_orders.items():
        orders_df = transform.transform_orders(orders, store_id)
        refunds_df = transform.transform_refunds(orders, store_id)
        
        all_orders.append(orders_df)
        all_refunds.append(refunds_df)
        
        console.print(f"  {store_id}: {len(orders_df)} orders, {len(refunds_df)} refunds")
    
    # Filter out empty DataFrames before concat
    non_empty_orders = [df for df in all_orders if not df.empty]
    non_empty_refunds = [df for df in all_refunds if not df.empty]
    combined_orders = pd.concat(non_empty_orders, ignore_index=True) if non_empty_orders else pd.DataFrame()
    combined_refunds = pd.concat(non_empty_refunds, ignore_index=True) if non_empty_refunds else pd.DataFrame()
    
    # Save curated data
    transform.save_curated_data(combined_orders, combined_refunds, period_name, f"{data_dir}/curated")
    console.print()
    
    # Step 3: Aggregate
    console.print("[bold]Step 3: Aggregating by state...[/bold]")
    state_aggregates = aggregate.aggregate_by_state(combined_orders, combined_refunds)
    
    console.print(f"  Found data for {len(state_aggregates)} registered states")
    console.print()
    
    # Step 4: Reconcile
    console.print("[bold]Step 4: Running reconciliation checks...[/bold]")
    exceptions = reconcile.detect_exceptions(combined_orders, combined_refunds)
    exceptions_summary = reconcile.summarize_exceptions(exceptions)

    if len(exceptions) > 0:
        exc_path = reconcile.save_exceptions(exceptions, period_name, f"{data_dir}/outputs")
        console.print(f"  [yellow]Found {len(exceptions)} exceptions[/yellow]")
        console.print(f"  Saved to: {exc_path}")
        for exc_type, data in exceptions_summary.get("by_type", {}).items():
            console.print(f"    - {exc_type}: {data['count']}")
    else:
        console.print("  [green]No exceptions detected[/green]")
    console.print()

    # Step 5: Render outputs
    console.print("[bold]Step 5: Generating filing packets...[/bold]")
    output_dir = f"{data_dir}/outputs"

    for state, state_data in state_aggregates.items():
        # State summary CSV
        csv_path = render.render_state_summary_csv(state, state_data, period_name, output_dir)
        console.print(f"  [green]Created: {csv_path}[/green]")

        # Filing packet MD
        # Filter exceptions for this state
        state_exceptions = reconcile.filter_exceptions_by_state(exceptions, state)
        state_exc_summary = reconcile.summarize_exceptions(state_exceptions)
        
        md_path = render.render_filing_packet_md(
            state, state_data, state_exc_summary, period_name, stores_config, output_dir
        )
        console.print(f"  [green]Created: {md_path}[/green]")
        
        # Store detail CSVs
        for store_id in state_data.get("store_breakdown", {}).keys():
            store_state_orders = combined_orders[
                (combined_orders["store_id"] == store_id) & 
                (combined_orders["state"] == state)
            ]
            if len(store_state_orders) > 0:
                detail_path = render.render_store_detail_csv(
                    store_id, state, store_state_orders, period_name, output_dir
                )
    
    console.print()
    console.print("[bold green]Filing run complete![/bold green]")
    
    # Summary table
    table = Table(title=f"Summary for {period_name}")
    table.add_column("State", style="cyan")
    table.add_column("Orders", justify="right")
    table.add_column("Total Sales", justify="right")
    table.add_column("Tax Collected", justify="right")
    table.add_column("Net Tax Due", justify="right", style="green")
    
    for state, data in sorted(state_aggregates.items()):
        table.add_row(
            state,
            str(data["order_count"]),
            f"${data['total_sales']:,.2f}",
            f"${data['tax_collected']:,.2f}",
            f"${data['net_tax_due']:,.2f}"
        )
    
    console.print(table)


@app.command()
def nexus_report(
    as_of_date: str = typer.Option(None, help="Date for analysis (YYYY-MM-DD), defaults to today"),
    config_dir: str = typer.Option("config", help="Configuration directory"),
    data_dir: str = typer.Option("data", help="Data directory"),
    skip_extract: bool = typer.Option(True, help="Use existing curated data instead of extracting"),
):
    """Generate economic nexus status report."""
    console.print("[bold blue]Tax Agent - Nexus Status Report[/bold blue]")
    console.print()
    
    # Parse date
    if as_of_date:
        analysis_date = datetime.strptime(as_of_date, "%Y-%m-%d")
    else:
        analysis_date = datetime.now()
    
    console.print(f"Analysis date: {analysis_date.date()}")
    console.print()
    
    # Load 12 months of curated data
    console.print("[bold]Loading order data...[/bold]")

    curated_dir = Path(data_dir) / "curated"
    
    # Find all curated order files
    all_orders = []
    for orders_file in curated_dir.glob("*/orders.csv"):
        df = pd.read_csv(orders_file)
        all_orders.append(df)
        console.print(f"  Loaded {len(df)} orders from {orders_file.parent.name}")
    
    if not all_orders:
        console.print("[red]No curated data found. Run 'run' command first to extract data.[/red]")
        raise typer.Exit(1)
    
    combined_orders = pd.concat(all_orders, ignore_index=True)
    console.print(f"  Total: {len(combined_orders)} orders")
    console.print()
    
    # Calculate nexus status
    console.print("[bold]Calculating nexus status...[/bold]")
    nexus_status = nexus.calculate_nexus_status(combined_orders, analysis_date)
    action_items = nexus.get_action_items(nexus_status)
    
    # Generate reports
    console.print("[bold]Generating reports...[/bold]")
    output_dir = f"{data_dir}/outputs"
    
    md_path = render.render_nexus_report_md(nexus_status, action_items, analysis_date, output_dir)
    console.print(f"  [green]Created: {md_path}[/green]")
    
    csv_path = render.render_nexus_report_csv(nexus_status, analysis_date, output_dir)
    console.print(f"  [green]Created: {csv_path}[/green]")
    
    console.print()
    
    # Display action items
    if action_items:
        console.print("[bold yellow]Action Required:[/bold yellow]")
        action_table = Table()
        action_table.add_column("State", style="cyan")
        action_table.add_column("Priority", style="red")
        action_table.add_column("Action")
        action_table.add_column("Sales", justify="right")
        action_table.add_column("% of Threshold", justify="right")
        
        for item in action_items:
            action_table.add_row(
                item["state"],
                item["priority"],
                item["action"],
                f"${item['sales']:,.2f}",
                f"{item['sales_percentage']:.1f}%"
            )
        
        console.print(action_table)
    else:
        console.print("[green]No states require immediate action.[/green]")
    
    console.print()
    console.print("[bold green]Nexus report complete![/bold green]")


@app.command()
def validate_config(
    config_dir: str = typer.Option("config", help="Configuration directory"),
):
    """Validate configuration files."""
    console.print("[bold blue]Validating configuration...[/bold blue]")
    console.print()
    
    errors = []
    warnings = []
    
    # Check stores.yaml
    stores_path = Path(config_dir) / "stores.yaml"
    if stores_path.exists():
        with open(stores_path) as f:
            stores = yaml.safe_load(f)
        
        console.print("[green]✓[/green] stores.yaml exists")
        
        for store_id, config in stores.get("stores", {}).items():
            domain_env = config.get("domain_env")
            token_env = config.get("token_env")
            
            if not os.environ.get(domain_env):
                errors.append(f"Missing environment variable: {domain_env} (for {store_id})")
            else:
                console.print(f"  [green]✓[/green] {store_id}: domain configured")
            
            if not os.environ.get(token_env):
                errors.append(f"Missing environment variable: {token_env} (for {store_id})")
            else:
                console.print(f"  [green]✓[/green] {store_id}: token configured")
    else:
        errors.append("stores.yaml not found")
    
    # Check registrations.yaml
    reg_path = Path(config_dir) / "registrations.yaml"
    if reg_path.exists():
        with open(reg_path) as f:
            registrations = yaml.safe_load(f)
        
        console.print("[green]✓[/green] registrations.yaml exists")
        
        registered = [s for s, c in registrations.get("registrations", {}).items() if c.get("registered")]
        console.print(f"  Registered states: {', '.join(sorted(registered))}")
    else:
        warnings.append("registrations.yaml not found (using defaults)")
    
    # Check other configs
    for config_name in ["mappings.yaml", "nexus_thresholds.yaml"]:
        config_path = Path(config_dir) / config_name
        if config_path.exists():
            console.print(f"[green]✓[/green] {config_name} exists")
        else:
            warnings.append(f"{config_name} not found (using defaults)")
    
    console.print()
    
    if warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for w in warnings:
            console.print(f"  [yellow]![/yellow] {w}")
        console.print()
    
    if errors:
        console.print("[red]Errors:[/red]")
        for e in errors:
            console.print(f"  [red]✗[/red] {e}")
        raise typer.Exit(1)
    
    console.print("[bold green]Configuration valid![/bold green]")


def main():
    app()


if __name__ == "__main__":
    main()
