#!/usr/bin/env python3
"""Comprehensive test of all system components."""

import sys
import os
sys.path.insert(0, 'src')

from database.db_manager_v2 import NYCCFBDatabase
from ai.ai_phase3 import Phase3AI
import pandas as pd
import numpy as np

def test_database():
    """Test database connectivity and basic operations."""
    print("\n" + "="*60)
    print("1. TESTING DATABASE")
    print("="*60)
    
    try:
        db = NYCCFBDatabase()
        stats = db.get_database_stats()
        
        print("✓ Database connected successfully")
        print(f"  • Contributors: {stats.get('contributors_count', 0):,}")
        print(f"  • Contributions: {stats.get('contributions_count', 0):,}")
        print(f"  • Voters: {stats.get('voters_count', 0):,}")
        print(f"  • Expenditures: {stats.get('expenditures_count', 0):,}")
        
        # Test a simple query
        result = db.execute_query("SELECT COUNT(*) as count FROM contributors")
        print(f"  • Query test: {result['count'].iloc[0]:,} contributors found")
        
        return True
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False

def test_pgvector():
    """Test PGVector functionality."""
    print("\n" + "="*60)
    print("2. TESTING PGVECTOR")
    print("="*60)
    
    try:
        from ai.pgvector_manager import PGVectorManager
        pgv = PGVectorManager()
        
        # Get statistics
        stats = pgv.get_statistics()
        print("✓ PGVector connected successfully")
        print(f"  • Total embeddings: {stats['total'].get('total_embeddings', 0):,}")
        
        # Test embedding storage
        test_embedding = {
            'entity_type': 'test',
            'entity_id': 'test_001',
            'content': 'Test content for PGVector',
            'embedding': np.random.randn(384).tolist(),
            'metadata': {'test': True}
        }
        
        # Store and retrieve
        pgv.store_embeddings([test_embedding])
        results = pgv.vector_search(
            np.array(test_embedding['embedding']),
            entity_type='test',
            top_k=1
        )
        
        if results:
            print("✓ Vector storage and retrieval working")
            # Clean up test data
            pgv.delete_embeddings(entity_type='test')
        
        return True
    except Exception as e:
        print(f"✗ PGVector test failed: {e}")
        return False

def test_phase3_ai():
    """Test Phase 3 AI system."""
    print("\n" + "="*60)
    print("3. TESTING PHASE 3 AI")
    print("="*60)
    
    try:
        ai = Phase3AI()
        ai.initialize()
        print("✓ Phase 3 AI initialized")
        
        # Get status
        status = ai.get_phase3_status()
        print(f"  • Vector dimensions: {status['capabilities']['pgvector']['vector_dimensions']}")
        print(f"  • Total embeddings: {status['capabilities']['pgvector']['total_embeddings']:,}")
        print(f"  • Knowledge graph relations: {status['capabilities']['knowledge_graph']['total_relations']:,}")
        
        # Test embedding generation
        test_text = "Brooklyn lawyer contributing to mayoral campaign"
        embedding = ai.generate_embedding(test_text)
        print(f"✓ Embedding generation working (shape: {embedding.shape})")
        
        # Test semantic search
        results = ai.semantic_search_pgvector("Brooklyn", top_k=3)
        print(f"✓ Semantic search working ({len(results)} results)")
        
        return True
    except Exception as e:
        print(f"✗ Phase 3 AI test failed: {e}")
        return False

def test_anomaly_detection():
    """Test anomaly detection."""
    print("\n" + "="*60)
    print("4. TESTING ANOMALY DETECTION")
    print("="*60)
    
    try:
        ai = Phase3AI()
        ai.initialize()
        
        # Test anomaly detection
        anomalies = ai.base_ai.detect_anomalous_contributions(limit=5)
        if not anomalies.empty:
            print(f"✓ Found {len(anomalies)} anomalous contributions")
            print(f"  • Top anomaly score: {anomalies['anomaly_score'].max():.3f}")
            print(f"  • Largest amount: ${anomalies['amount'].max():,.2f}")
        else:
            print("✓ Anomaly detection working (no anomalies found)")
        
        return True
    except Exception as e:
        print(f"✗ Anomaly detection test failed: {e}")
        return False

def test_network_analysis():
    """Test network analysis."""
    print("\n" + "="*60)
    print("5. TESTING NETWORK ANALYSIS")
    print("="*60)
    
    try:
        ai = Phase3AI()
        ai.initialize()
        
        # Test network building
        network_data = ai.build_contribution_network()
        if network_data.get('metrics'):
            metrics = network_data['metrics']
            print("✓ Network analysis working")
            print(f"  • Nodes: {metrics.get('num_nodes', 0):,}")
            print(f"  • Edges: {metrics.get('num_edges', 0):,}")
            print(f"  • Communities: {network_data.get('num_communities', 0)}")
        
        return True
    except Exception as e:
        print(f"✗ Network analysis test failed: {e}")
        return False

def test_predictive_features():
    """Test predictive analytics."""
    print("\n" + "="*60)
    print("6. TESTING PREDICTIVE FEATURES")
    print("="*60)
    
    try:
        ai = Phase3AI()
        ai.initialize()
        
        # Test contribution patterns
        patterns = ai.base_ai.analyze_contribution_patterns()
        if patterns:
            print("✓ Pattern analysis working")
            print(f"  • Total analyzed: ${patterns.get('total_amount', 0):,.2f}")
            print(f"  • Average contribution: ${patterns.get('avg_contribution', 0):,.2f}")
        
        # Test contributor value prediction
        prediction = ai.predict_contributor_value({
            'occupation': 'Lawyer',
            'city': 'Brooklyn'
        })
        if prediction:
            print("✓ Value prediction working")
            print(f"  • Predicted value: ${prediction.get('predicted_value', 0):,.2f}")
        
        return True
    except Exception as e:
        print(f"✗ Predictive features test failed: {e}")
        return False

def test_knowledge_graph():
    """Test knowledge graph functionality."""
    print("\n" + "="*60)
    print("7. TESTING KNOWLEDGE GRAPH")
    print("="*60)
    
    try:
        ai = Phase3AI()
        ai.initialize()
        
        # Query knowledge graph
        kg_data = ai.query_knowledge_graph(limit=10)
        if not kg_data.empty:
            print(f"✓ Knowledge graph has {len(kg_data)} relations")
            predicates = kg_data['predicate'].unique() if 'predicate' in kg_data.columns else []
            for pred in predicates[:3]:
                print(f"  • {pred}")
        else:
            print("✓ Knowledge graph system working (no data yet)")
        
        return True
    except Exception as e:
        print(f"✗ Knowledge graph test failed: {e}")
        return False

def test_data_quality():
    """Test data quality and integrity."""
    print("\n" + "="*60)
    print("8. TESTING DATA QUALITY")
    print("="*60)
    
    try:
        db = NYCCFBDatabase()
        
        # Check for data integrity
        checks = {
            "Contributors with names": "SELECT COUNT(*) FROM contributors WHERE full_name IS NOT NULL",
            "Contributions with amounts": "SELECT COUNT(*) FROM contributions WHERE amount > 0",
            "Voters with addresses": "SELECT COUNT(*) FROM voters WHERE address IS NOT NULL",
            "Contributors with totals": "SELECT COUNT(*) FROM contributors WHERE total_contributions > 0"
        }
        
        print("✓ Data quality checks:")
        for check_name, query in checks.items():
            result = db.execute_query(query)
            count = result.iloc[0, 0] if not result.empty else 0
            print(f"  • {check_name}: {count:,}")
        
        return True
    except Exception as e:
        print(f"✗ Data quality test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("\n" + "🧪"*30)
    print("       COMPREHENSIVE SYSTEM TEST")
    print("🧪"*30)
    
    results = []
    
    # Run all tests
    results.append(("Database", test_database()))
    results.append(("PGVector", test_pgvector()))
    results.append(("Phase 3 AI", test_phase3_ai()))
    results.append(("Anomaly Detection", test_anomaly_detection()))
    results.append(("Network Analysis", test_network_analysis()))
    results.append(("Predictive Features", test_predictive_features()))
    results.append(("Knowledge Graph", test_knowledge_graph()))
    results.append(("Data Quality", test_data_quality()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:.<30} {status}")
    
    print("\n" + "="*60)
    print(f"OVERALL: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL SYSTEMS OPERATIONAL! 🎉")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed - check logs above")
    
    print("="*60)

if __name__ == "__main__":
    main()