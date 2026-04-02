# Knowledge of GraphDBA
> Author: Hunky Hsu

## 1. Data Access Security Layer
> This layer mainly in /mcp_servers/security_utils.py

A Standard data access security layer is composed of 7 modules: 
- Network Isolation: VPC, IP White List
- Identity & RBAC: JWT, Read-only database account
- Intent & Syntax Validation: SQL injection detection
- Execution Sandbox: Read-only transaction wrapper
- Resource Circuit Breakers: Add query timeout enforcement + Implement row limit injector
- Egress/Exfiltration Control: Create DLP validator for sensitive data patterns
- Audit Logging: 

