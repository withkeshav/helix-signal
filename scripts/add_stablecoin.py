#!/usr/bin/env python3
"""
Script to add a new stablecoin asset to Helix Signal.

This script automates the process of adding a new stablecoin asset by:
1. Adding the asset to config/assets.json
2. Adding DexScreener addresses for the asset (if applicable)
3. Updating documentation
4. Validating the configuration
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

def load_json_file(file_path: Path) -> Any:
    """Load JSON file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON in {file_path}: {e}")
        return None

def save_json_file(file_path: Path, data: Any) -> bool:
    """Save JSON file with proper formatting."""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving JSON to {file_path}: {e}")
        return False

def validate_asset_config(symbol: str, name: str, defillama_symbol: str, peg_type: str) -> bool:
    """Validate asset configuration parameters."""
    if not symbol or len(symbol) < 2 or len(symbol) > 16:
        print("Error: Symbol must be between 2 and 16 characters")
        return False
    
    if not name or len(name) < 3:
        print("Error: Name must be at least 3 characters")
        return False
    
    if not defillama_symbol:
        print("Error: DefiLlama symbol is required")
        return False
    
    valid_peg_types = ["peggedUSD", "peggedEUR", "peggedBTC", "peggedGBP", "peggedJPY", "peggedCNY"]
    if peg_type not in valid_peg_types:
        print(f"Error: Peg type must be one of {valid_peg_types}")
        return False
    
    valid_types = ["fiat_backed", "crypto_collateralized", "yield_bearing", "algorithmic"]
    
    return True

def add_asset_to_config(
    symbol: str, 
    name: str, 
    defillama_symbol: str,
    peg_type: str = "peggedUSD",
    enabled: bool = True,
    stablecoin_type: str = "fiat_backed",
) -> bool:
    """Add asset to config/assets.json."""
    config_path = Path("config/assets.json")
    assets = load_json_file(config_path)
    
    if assets is None:
        return False
    
    if stablecoin_type not in valid_types:
        print(f"Error: Type must be one of {valid_types}")
        return False
    
    # Check if asset already exists
    for asset in assets:
        if asset.get("symbol", "").upper() == symbol.upper():
            print(f"Asset {symbol} already exists in config")
            return False
    
    # Validate the configuration
    if not validate_asset_config(symbol, name, defillama_symbol, peg_type):
        return False
    
    # Add new asset
    new_asset = {
        "symbol": symbol.upper(),
        "name": name,
        "defillama_symbol": defillama_symbol,
        "peg_type": peg_type,
        "enabled": enabled,
        "default": False,  # New assets are not default
        "type": stablecoin_type,
    }
    
    assets.append(new_asset)
    if save_json_file(config_path, assets):
        print(f"Added {symbol} to config/assets.json")
        return True
    else:
        print(f"Failed to save {symbol} to config/assets.json")
        return False

def get_dexscreener_addresses(symbol: str) -> Dict[str, str]:
    """Get DexScreener addresses for common chains."""
    # This would typically be a lookup from a database or API
    # For now, we'll return a placeholder
    print(f"Note: You may need to manually add DexScreener addresses for {symbol}")
    print("Common chains: ethereum, solana, bsc, polygon, arbitrum, avalanche")
    return {}

def add_dexscreener_addresses(symbol: str, addresses: Dict[str, str]) -> bool:
    """Add DexScreener addresses for the asset."""
    dexscreener_path = Path("backend/sources/dexscreener.py")
    
    if not dexscreener_path.exists():
        print("DexScreener source file not found")
        return False
    
    # Read the file
    try:
        with open(dexscreener_path, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading dexscreener.py: {e}")
        return False
    
    # For now, we'll just inform the user to manually add addresses
    # In a more advanced version, we could parse and modify the STABLECOIN_ADDRESSES dict
    if addresses:
        print(f"Please manually add the following addresses to {dexscreener_path}:")
        for chain, address in addresses.items():
            print(f"  {chain}: {address}")
    
    return True

def update_readme(symbol: str, name: str) -> bool:
    """Update README with new asset."""
    readme_path = Path("README.md")
    if not readme_path.exists():
        print("README.md not found")
        return False
    
    try:
        with open(readme_path, 'r') as f:
            content = f.read()
        
        # Check if asset is already mentioned
        if symbol.upper() in content:
            print(f"{symbol} already mentioned in README.md")
            return True
        
        # Add to supported assets section if it exists
        lines = content.split('\n')
        new_lines = []
        asset_section_found = False
        
        for line in lines:
            new_lines.append(line)
            if "Supported Assets" in line or "supported assets" in line.lower():
                asset_section_found = True
                # Add the new asset
                new_lines.append(f"- **{symbol}** - {name}")
        
        if not asset_section_found:
            print("Could not find 'Supported Assets' section in README.md")
            return False
        
        with open(readme_path, 'w') as f:
            f.write('\n'.join(new_lines))
        
        print(f"Updated README.md with {symbol}")
        return True
    except Exception as e:
        print(f"Error updating README.md: {e}")
        return False

def validate_configuration(symbol: str) -> bool:
    """Validate that the new asset configuration is correct."""
    config_path = Path("config/assets.json")
    assets = load_json_file(config_path)
    
    if assets is None:
        return False
    
    # Check if asset exists
    asset_found = False
    for asset in assets:
        if asset.get("symbol", "").upper() == symbol.upper():
            asset_found = True
            print(f"✅ Found asset {symbol} in configuration")
            print(f"   Name: {asset.get('name', 'N/A')}")
            print(f"   DefiLlama Symbol: {asset.get('defillama_symbol', 'N/A')}")
            print(f"   Peg Type: {asset.get('peg_type', 'N/A')}")
            print(f"   Enabled: {asset.get('enabled', False)}")
            break
    
    if not asset_found:
        print(f"❌ Asset {symbol} not found in configuration")
        return False
    
    return True

def main():
    """Main function to add a new stablecoin."""
    parser = argparse.ArgumentParser(description="Add a new stablecoin to Helix Signal")
    parser.add_argument("symbol", help="Asset symbol (e.g. USDD)")
    parser.add_argument("name", help="Full asset name (e.g. 'Decentralized USD')")
    parser.add_argument("defillama_symbol", nargs="?", default=None, help="DefiLlama symbol (defaults to symbol)")
    parser.add_argument("peg_type", nargs="?", default="peggedUSD", help="Peg type (default: peggedUSD)")
    parser.add_argument("--type", dest="stablecoin_type", default="fiat_backed",
                        choices=["fiat_backed", "crypto_collateralized", "yield_bearing", "algorithmic"],
                        help="Stablecoin type taxonomy (default: fiat_backed)")
    args = parser.parse_args()
    
    symbol = args.symbol
    name = args.name
    defillama_symbol = args.defillama_symbol or symbol
    peg_type = args.peg_type
    
    valid_types = ["fiat_backed", "crypto_collateralized", "yield_bearing", "algorithmic"]
    if args.stablecoin_type not in valid_types:
        print(f"Error: --type must be one of {valid_types}")
        sys.exit(1)
    
    print(f"Adding new stablecoin asset: {symbol}")
    print(f"Name: {name}")
    print(f"DefiLlama Symbol: {defillama_symbol}")
    print(f"Peg Type: {peg_type}")
    print(f"Type: {args.stablecoin_type}")
    
    # Add to config
    if not add_asset_to_config(symbol, name, defillama_symbol, peg_type, stablecoin_type=args.stablecoin_type):
        print("Failed to add asset to configuration")
        sys.exit(1)
    
    # Get DexScreener addresses (this would be more sophisticated in practice)
    addresses = get_dexscreener_addresses(symbol)
    add_dexscreener_addresses(symbol, addresses)
    
    # Update README
    update_readme(symbol, name)
    
    # Validate configuration
    if validate_configuration(symbol):
        print(f"\n✅ Successfully added {symbol}!")
        print("Next steps:")
        print("1. Restart the backend service: docker compose restart backend")
        print("2. Check the logs to ensure the new asset is being processed")
        print("3. Verify data is appearing in the frontend")
        print("4. Add DexScreener contract addresses if needed")
    else:
        print(f"\n⚠️  Added {symbol} but validation failed")
        sys.exit(1)

if __name__ == "__main__":
    main()