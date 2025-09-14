"""
URL loading utility for freeMarkable.

This module provides functionality to load and parse URLs from the url.weblist file,
making them available for dynamic loading throughout the application.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional


class URLLoader:
    """
    Utility class for loading URLs from the url.weblist file.
    
    Parses the weblist file and provides structured access to URLs by category.
    """
    
    def __init__(self, weblist_path: Optional[Path] = None):
        """
        Initialize URL loader.
        
        Args:
            weblist_path: Path to url.weblist file. If None, uses default location.
        """
        if weblist_path is None:
            # Default to resources/url.weblist relative to this module
            weblist_path = Path(__file__).parent.parent.parent / "url.weblist"
        
        self.weblist_path = Path(weblist_path)
        self.urls: Dict[str, List[str]] = {}
        self._logger = logging.getLogger(__name__)
        
        # Load URLs on initialization
        self._load_urls()
    
    def _load_urls(self) -> None:
        """Load and parse URLs from the weblist file."""
        if not self.weblist_path.exists():
            self._logger.warning(f"URL weblist file not found: {self.weblist_path}")
            return
        
        try:
            with open(self.weblist_path, 'r', encoding='utf-8') as f:
                current_category = "general"
                self.urls[current_category] = []
                
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        # Check if this is a category comment
                        if line.startswith('#') and 'URLs' in line:
                            # Extract category name from comment
                            category = line.replace('#', '').strip().lower()
                            category = category.replace(' urls', '').replace(' architecture', '').strip()
                            if category and category not in self.urls:
                                current_category = category
                                self.urls[current_category] = []
                        continue
                    
                    # Add URL to current category
                    if line.startswith('http'):
                        self.urls[current_category].append(line)
                
            self._logger.info(f"Loaded {sum(len(urls) for urls in self.urls.values())} URLs from {len(self.urls)} categories")
            
        except Exception as e:
            self._logger.error(f"Failed to load URLs from {self.weblist_path}: {e}")
    
    def get_urls_by_category(self, category: str) -> List[str]:
        """
        Get all URLs for a specific category.
        
        Args:
            category: Category name (e.g., 'arm32', 'aarch64', 'api')
            
        Returns:
            List of URLs for the category
        """
        return self.urls.get(category.lower(), [])
    
    def get_url_by_pattern(self, pattern: str, category: Optional[str] = None) -> Optional[str]:
        """
        Get the first URL matching a pattern, optionally within a specific category.
        
        Args:
            pattern: Pattern to search for in URLs (e.g., 'xovi-extensions', 'appload')
            category: Optional category to search within
            
        Returns:
            First matching URL or None if not found
        """
        categories_to_search = [category.lower()] if category else self.urls.keys()
        
        for cat in categories_to_search:
            if cat in self.urls:
                for url in self.urls[cat]:
                    if pattern.lower() in url.lower():
                        return url
        
        return None
    
    def get_architecture_urls(self) -> Dict[str, Dict[str, str]]:
        """
        Get architecture-specific URLs organized by component.
        
        Returns:
            Dictionary with architecture mappings for components
        """
        arch_urls = {
            "arm32": {},
            "aarch64": {}
        }
        
        # ARM32 URLs
        arm32_urls = self.get_urls_by_category("arm32")
        for url in arm32_urls:
            if "xovi-extensions" in url:
                arch_urls["arm32"]["xovi_extensions"] = url
            elif "appload" in url and "xovi-extensions" not in url:
                arch_urls["arm32"]["appload"] = url
            elif "xovi" in url and "xovi-extensions" not in url and "tripletap" not in url:
                arch_urls["arm32"]["xovi_binary"] = url
            elif "koreader" in url:
                arch_urls["arm32"]["koreader"] = url
        
        # AARCH64 URLs
        aarch64_urls = self.get_urls_by_category("aarch64")
        for url in aarch64_urls:
            if "xovi-extensions" in url:
                arch_urls["aarch64"]["xovi_extensions"] = url
            elif "appload" in url and "xovi-extensions" not in url:
                arch_urls["aarch64"]["appload"] = url
            elif "xovi" in url and "xovi-extensions" not in url and "tripletap" not in url:
                arch_urls["aarch64"]["xovi_binary"] = url
            elif "koreader" in url:
                arch_urls["aarch64"]["koreader"] = url
        
        return arch_urls
    
    def get_api_urls(self) -> Dict[str, str]:
        """
        Get API URLs with placeholders.
        
        Returns:
            Dictionary of API URL templates
        """
        api_urls = {}
        api_category_urls = self.get_urls_by_category("api")
        
        for url in api_category_urls:
            if "releases/latest" in url:
                api_urls["releases_latest"] = url
            elif "releases" not in url and "{github_repo}" in url:
                api_urls["repo_info"] = url
        
        return api_urls
    
    def get_additional_urls(self) -> Dict[str, str]:
        """
        Get additional download URLs.
        
        Returns:
            Dictionary of additional URLs
        """
        additional_urls = {}
        additional_category_urls = self.get_urls_by_category("additional download")
        
        for url in additional_category_urls:
            if "appload.so" in url:
                additional_urls["appload_extension"] = url
            elif "rm-literm" in url and "{literm_filename}" in url:
                additional_urls["literm_binary"] = url
            elif "literm.qmd" in url:
                additional_urls["literm_qmd"] = url
        
        return additional_urls
    
    def get_general_urls(self) -> Dict[str, str]:
        """
        Get general URLs (GitHub repos, documentation, etc.).
        
        Returns:
            Dictionary of general URLs
        """
        general_urls = {}
        
        # Get GitHub repository URLs
        github_urls = self.get_urls_by_category("github repository")
        if github_urls:
            general_urls["freemarkable_repo"] = github_urls[0] if github_urls else ""
        
        # Get tripletap URL from ARM32 category (it's architecture-independent)
        arm32_urls = self.get_urls_by_category("arm32")
        for url in arm32_urls:
            if "tripletap" in url:
                general_urls["xovi_tripletap"] = url
                break
        
        return general_urls


# Global URL loader instance
_global_url_loader: Optional[URLLoader] = None


def get_url_loader() -> URLLoader:
    """
    Get the global URL loader instance.
    
    Returns:
        Global URLLoader instance
    """
    global _global_url_loader
    if _global_url_loader is None:
        _global_url_loader = URLLoader()
    return _global_url_loader


def init_url_loader(weblist_path: Optional[Path] = None) -> URLLoader:
    """
    Initialize the global URL loader.
    
    Args:
        weblist_path: Path to url.weblist file
        
    Returns:
        Initialized URLLoader instance
    """
    global _global_url_loader
    _global_url_loader = URLLoader(weblist_path)
    return _global_url_loader