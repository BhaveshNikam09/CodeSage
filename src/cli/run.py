import sys
import argparse
from engine.analyzer import StaticAnalyzer
from engine.report_builder import ReportBuilder

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='CodeSage - AI Code Reviewer CLI')
    parser.add_argument('file', help='Python file to analyze')
    parser.add_argument('--format', choices=['json', 'html'], default='json')
    parser.add_argument('--output', help='Output file path')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🔍 CodeSage Analysis")
    print("=" * 70)
    
    # Read file
    try:
        with open(args.file, 'r') as f:
            code = f.read()
    except FileNotFoundError:
        print(f"❌ Error: File '{args.file}' not found")
        sys.exit(1)
    
    # Analyze
    analyzer = StaticAnalyzer()
    results = analyzer.analyze(code)
    
    # Generate report
    if args.format == 'json':
        report = ReportBuilder.generate_json(results, args.output)
        if not args.output:
            print(report)
    else:
        report = ReportBuilder.generate_html(results)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(report)
            print(f"✅ HTML report saved to: {args.output}")
    
    # Summary
    print(f"\n📊 Summary:")
    print(f"  Score: {results['summary']['score']}/100")
    print(f"  Issues: {results['statistics']['total_issues']}")
    print(f"  Critical: {results['statistics']['critical']}")

if __name__ == '__main__':
    main()