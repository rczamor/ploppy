import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class ComplianceChecker:
    """Check political contribution data for compliance with regulations."""
    
    def __init__(self):
        # Federal contribution limits (example values - should be updated based on current regulations)
        self.federal_limits = {
            'individual_to_candidate_primary': 3300,
            'individual_to_candidate_general': 3300,
            'individual_to_pac_per_year': 5000,
            'individual_to_party_per_year': 36500,
            'individual_total_per_cycle': 140000
        }
        
        # State-specific limits (simplified example)
        self.state_limits = {
            'CA': {'individual_to_candidate': 4900},
            'NY': {'individual_to_candidate': 3100},
            'TX': {'individual_to_candidate': float('inf')},  # No limit
            'FL': {'individual_to_candidate': 1000}
        }
    
    def check_compliance(self, df):
        """Perform comprehensive compliance checking."""
        try:
            compliance_results = {
                'overall_score': 0.0,
                'checks': {},
                'violations': [],
                'recommendations': []
            }
            
            # Run individual compliance checks
            checks = [
                ('contribution_limits', self._check_contribution_limits),
                ('data_completeness', self._check_data_completeness),
                ('duplicate_detection', self._check_duplicates),
                ('date_validation', self._check_date_validity),
                ('amount_validation', self._check_amount_validity),
                ('name_validation', self._check_name_validity)
            ]
            
            passed_checks = 0
            total_checks = len(checks)
            
            for check_name, check_function in checks:
                try:
                    result = check_function(df)
                    compliance_results['checks'][check_name] = result
                    if result['passed']:
                        passed_checks += 1
                except Exception as e:
                    compliance_results['checks'][check_name] = {
                        'passed': False,
                        'message': f'Check failed: {str(e)}'
                    }
            
            # Calculate overall score
            compliance_results['overall_score'] = passed_checks / total_checks
            
            # Generate recommendations
            compliance_results['recommendations'] = self._generate_recommendations(compliance_results)
            
            return compliance_results
            
        except Exception as e:
            raise Exception(f"Compliance check failed: {str(e)}")
    
    def _check_contribution_limits(self, df):
        """Check for violations of contribution limits."""
        violations = []
        
        try:
            # Check individual donor limits per recipient
            if 'recipient' in df.columns:
                donor_recipient_totals = df.groupby(['donor_name', 'recipient'])['amount'].sum()
                
                # Check against general limit (using federal primary limit as example)
                limit = self.federal_limits['individual_to_candidate_primary']
                over_limit = donor_recipient_totals[donor_recipient_totals > limit]
                
                for (donor, recipient), amount in over_limit.items():
                    violations.append({
                        'donor': donor,
                        'recipient': recipient,
                        'amount': amount,
                        'limit': limit,
                        'excess': amount - limit,
                        'violation_type': 'Individual contribution limit exceeded'
                    })
            
            # Check annual donor totals
            current_year = datetime.now().year
            current_year_data = df[df['date'].dt.year == current_year] if 'date' in df.columns else df
            
            annual_donor_totals = current_year_data.groupby('donor_name')['amount'].sum()
            annual_limit = self.federal_limits['individual_total_per_cycle']
            over_annual_limit = annual_donor_totals[annual_donor_totals > annual_limit]
            
            for donor, amount in over_annual_limit.items():
                violations.append({
                    'donor': donor,
                    'amount': amount,
                    'limit': annual_limit,
                    'excess': amount - annual_limit,
                    'violation_type': 'Annual contribution limit exceeded'
                })
            
            result = {
                'passed': len(violations) == 0,
                'message': f'Found {len(violations)} contribution limit violations' if violations else 'All contributions within limits',
                'violations_count': len(violations)
            }
            
            if violations:
                result['violations'] = pd.DataFrame(violations)
            
            return result
            
        except Exception as e:
            return {
                'passed': False,
                'message': f'Contribution limit check failed: {str(e)}'
            }
    
    def _check_data_completeness(self, df):
        """Check for data completeness issues."""
        required_fields = ['donor_name', 'amount', 'date']
        optional_fields = ['recipient', 'city', 'state', 'zip']
        
        completeness_scores = {}
        issues = []
        
        # Check required fields
        for field in required_fields:
            if field in df.columns:
                null_count = df[field].isnull().sum()
                empty_count = (df[field] == '').sum() if df[field].dtype == 'object' else 0
                missing_count = null_count + empty_count
                completeness = 1 - (missing_count / len(df))
                completeness_scores[field] = completeness
                
                if completeness < 0.95:  # 95% completeness threshold
                    issues.append(f'{field}: {completeness:.1%} complete ({missing_count} missing)')
            else:
                completeness_scores[field] = 0
                issues.append(f'{field}: Column missing entirely')
        
        # Check optional fields
        for field in optional_fields:
            if field in df.columns:
                null_count = df[field].isnull().sum()
                empty_count = (df[field] == '').sum() if df[field].dtype == 'object' else 0
                missing_count = null_count + empty_count
                completeness = 1 - (missing_count / len(df))
                completeness_scores[field] = completeness
        
        overall_completeness = np.mean(list(completeness_scores.values()))
        
        return {
            'passed': len(issues) == 0,
            'message': f'Data completeness: {overall_completeness:.1%}' + (f' - Issues: {", ".join(issues)}' if issues else ''),
            'completeness_scores': completeness_scores,
            'issues': issues
        }
    
    def _check_duplicates(self, df):
        """Check for duplicate contributions."""
        # Define duplicate criteria (same donor, amount, date)
        duplicate_columns = ['donor_name', 'amount', 'date']
        available_columns = [col for col in duplicate_columns if col in df.columns]
        
        if len(available_columns) < 2:
            return {
                'passed': True,
                'message': 'Insufficient columns for duplicate detection'
            }
        
        duplicates = df[df.duplicated(subset=available_columns, keep=False)]
        duplicate_count = len(duplicates)
        
        # Also check for potential duplicates (same donor, similar amount, same day)
        potential_duplicates = []
        if 'donor_name' in df.columns and 'amount' in df.columns and 'date' in df.columns:
            for donor in df['donor_name'].unique():
                donor_data = df[df['donor_name'] == donor]
                if len(donor_data) > 1:
                    for date in donor_data['date'].dt.date.unique():
                        day_data = donor_data[donor_data['date'].dt.date == date]
                        if len(day_data) > 1:
                            # Check for amounts within $10 of each other
                            amounts = day_data['amount'].values
                            for i in range(len(amounts)):
                                for j in range(i+1, len(amounts)):
                                    if abs(amounts[i] - amounts[j]) <= 10:
                                        potential_duplicates.extend(day_data.index.tolist())
        
        result = {
            'passed': duplicate_count == 0,
            'message': f'Found {duplicate_count} exact duplicates, {len(set(potential_duplicates))} potential duplicates',
            'duplicate_count': duplicate_count,
            'potential_duplicate_count': len(set(potential_duplicates))
        }
        
        if duplicate_count > 0:
            result['duplicates'] = duplicates
        
        return result
    
    def _check_date_validity(self, df):
        """Check for date-related issues."""
        if 'date' not in df.columns:
            return {
                'passed': False,
                'message': 'Date column not found'
            }
        
        issues = []
        
        # Check for future dates
        future_dates = df[df['date'] > datetime.now()]
        if len(future_dates) > 0:
            issues.append(f'{len(future_dates)} contributions have future dates')
        
        # Check for very old dates (before 1970)
        old_dates = df[df['date'] < datetime(1970, 1, 1)]
        if len(old_dates) > 0:
            issues.append(f'{len(old_dates)} contributions have dates before 1970')
        
        # Check for null dates
        null_dates = df[df['date'].isnull()]
        if len(null_dates) > 0:
            issues.append(f'{len(null_dates)} contributions have missing dates')
        
        return {
            'passed': len(issues) == 0,
            'message': 'All dates valid' if len(issues) == 0 else f'Date issues: {", ".join(issues)}',
            'issues': issues
        }
    
    def _check_amount_validity(self, df):
        """Check for amount-related issues."""
        if 'amount' not in df.columns:
            return {
                'passed': False,
                'message': 'Amount column not found'
            }
        
        issues = []
        
        # Check for negative amounts
        negative_amounts = df[df['amount'] < 0]
        if len(negative_amounts) > 0:
            issues.append(f'{len(negative_amounts)} contributions have negative amounts')
        
        # Check for zero amounts
        zero_amounts = df[df['amount'] == 0]
        if len(zero_amounts) > 0:
            issues.append(f'{len(zero_amounts)} contributions have zero amounts')
        
        # Check for extremely large amounts (> $100,000)
        large_amounts = df[df['amount'] > 100000]
        if len(large_amounts) > 0:
            issues.append(f'{len(large_amounts)} contributions exceed $100,000')
        
        # Check for null amounts
        null_amounts = df[df['amount'].isnull()]
        if len(null_amounts) > 0:
            issues.append(f'{len(null_amounts)} contributions have missing amounts')
        
        return {
            'passed': len(issues) == 0,
            'message': 'All amounts valid' if len(issues) == 0 else f'Amount issues: {", ".join(issues)}',
            'issues': issues
        }
    
    def _check_name_validity(self, df):
        """Check for name-related issues."""
        if 'donor_name' not in df.columns:
            return {
                'passed': False,
                'message': 'Donor name column not found'
            }
        
        issues = []
        
        # Check for missing names
        missing_names = df[(df['donor_name'].isnull()) | (df['donor_name'] == '')]
        if len(missing_names) > 0:
            issues.append(f'{len(missing_names)} contributions have missing donor names')
        
        # Check for suspicious patterns
        suspicious_patterns = [
            'ANONYMOUS', 'UNKNOWN', 'TEST', 'SAMPLE', 'PLACEHOLDER'
        ]
        
        for pattern in suspicious_patterns:
            suspicious = df[df['donor_name'].str.contains(pattern, case=False, na=False)]
            if len(suspicious) > 0:
                issues.append(f'{len(suspicious)} contributions have suspicious names containing "{pattern}"')
        
        return {
            'passed': len(issues) == 0,
            'message': 'All names valid' if len(issues) == 0 else f'Name issues: {", ".join(issues)}',
            'issues': issues
        }
    
    def _generate_recommendations(self, compliance_results):
        """Generate compliance recommendations based on check results."""
        recommendations = []
        
        # Check overall compliance score
        score = compliance_results['overall_score']
        if score < 0.7:
            recommendations.append("Overall compliance is low. Consider comprehensive data review and cleanup.")
        elif score < 0.9:
            recommendations.append("Compliance is moderate. Address specific issues identified in failed checks.")
        
        # Specific recommendations based on failed checks
        checks = compliance_results['checks']
        
        if 'contribution_limits' in checks and not checks['contribution_limits']['passed']:
            recommendations.append("Review and remediate contribution limit violations. Consider implementing automated limit checking.")
        
        if 'data_completeness' in checks and not checks['data_completeness']['passed']:
            recommendations.append("Improve data collection processes to ensure required fields are complete.")
        
        if 'duplicate_detection' in checks and not checks['duplicate_detection']['passed']:
            recommendations.append("Implement duplicate detection and prevention measures in your data collection system.")
        
        if 'date_validation' in checks and not checks['date_validation']['passed']:
            recommendations.append("Review and correct date-related data quality issues.")
        
        if 'amount_validation' in checks and not checks['amount_validation']['passed']:
            recommendations.append("Validate and clean contribution amount data.")
        
        if 'name_validation' in checks and not checks['name_validation']['passed']:
            recommendations.append("Improve donor name data quality and validation processes.")
        
        # General recommendations
        recommendations.extend([
            "Consider implementing real-time compliance monitoring.",
            "Regular data quality audits are recommended.",
            "Maintain backup and audit trail of all contribution data."
        ])
        
        return recommendations[:5]  # Return top 5 recommendations
