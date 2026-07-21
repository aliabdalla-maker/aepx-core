# AEP-X Connector Catalogue — 107 Connectors

**Generated from** `connectors/catalogue.json` (single source of truth — regenerate this file rather than editing it).
**Architecture:** one coarse-grained service per category, one adapter per connector ([SOA-Architecture.md](SOA-Architecture.md) §3.1). `specialized` = working adapter with a concrete implementation path; `stub` = catalogued, routed, governed, returning canonical stub responses until a real integration lands.

**Total: 107 connectors across 11 categories.**

## enterprise (14)

| Connector | Protocols | AIA risk | Min trust | Maturity |
|---|---|---|---|---|
| sap | SOAP, REST | AIA-R2 | 60 | stub |
| salesforce | SOAP, REST | AIA-R1 | 50 | specialized |
| dynamics365 | REST | AIA-R2 | 60 | stub |
| oracle-erp | SOAP, REST | AIA-R2 | 60 | stub |
| workday | SOAP, REST | AIA-R2 | 60 | stub |
| servicenow | REST | AIA-R1 | 50 | stub |
| bamboohr | REST | AIA-R2 | 60 | stub |
| successfactors | REST | AIA-R2 | 60 | stub |
| xero | REST | AIA-R2 | 60 | stub |
| quickbooks | REST | AIA-R2 | 60 | stub |
| netsuite | SOAP, REST | AIA-R2 | 60 | stub |
| hubspot | REST | AIA-R1 | 50 | stub |
| sage | REST | AIA-R2 | 60 | stub |
| zoho-crm | REST | AIA-R1 | 50 | stub |

## productivity (11)

| Connector | Protocols | AIA risk | Min trust | Maturity |
|---|---|---|---|---|
| google-workspace | REST | AIA-R1 | 50 | stub |
| microsoft365 | REST | AIA-R1 | 50 | stub |
| slack | REST | AIA-R0 | 40 | specialized |
| teams | REST | AIA-R0 | 40 | stub |
| zoom | REST | AIA-R0 | 40 | stub |
| notion | REST | AIA-R0 | 40 | stub |
| confluence | REST | AIA-R0 | 40 | stub |
| trello | REST | AIA-R0 | 40 | stub |
| asana | REST | AIA-R0 | 40 | stub |
| monday | REST, GraphQL | AIA-R0 | 40 | stub |
| dropbox | REST | AIA-R1 | 50 | stub |

## devtools (11)

| Connector | Protocols | AIA risk | Min trust | Maturity |
|---|---|---|---|---|
| github | REST, GraphQL | AIA-R0 | 40 | specialized |
| gitlab | REST, GraphQL | AIA-R0 | 40 | stub |
| jira | REST | AIA-R0 | 40 | stub |
| azure-devops | REST | AIA-R0 | 40 | stub |
| bitbucket | REST | AIA-R0 | 40 | stub |
| jenkins | REST | AIA-R1 | 50 | stub |
| circleci | REST | AIA-R1 | 50 | stub |
| sonarqube | REST | AIA-R0 | 40 | stub |
| artifactory | REST | AIA-R1 | 50 | stub |
| dockerhub | REST | AIA-R0 | 40 | stub |
| terraform-cloud | REST | AIA-R1 | 50 | stub |

## aiplatform (14)

| Connector | Protocols | AIA risk | Min trust | Maturity |
|---|---|---|---|---|
| ml | REST | AIA-R1 | 40 | specialized |
| vllm | REST | AIA-R1 | 40 | stub |
| llamacpp | REST | AIA-R1 | 40 | stub |
| lmstudio | REST | AIA-R1 | 40 | stub |
| openai | REST | AIA-R1 | 40 | stub |
| anthropic | REST | AIA-R1 | 40 | stub |
| gemini | REST | AIA-R1 | 40 | stub |
| mistral | REST | AIA-R1 | 40 | stub |
| cohere | REST | AIA-R1 | 40 | stub |
| huggingface | REST | AIA-R1 | 40 | stub |
| bedrock | REST | AIA-R1 | 40 | stub |
| azure-openai | REST | AIA-R1 | 40 | stub |
| vertex-ai | REST | AIA-R1 | 40 | stub |
| deepseek | REST | AIA-R1 | 40 | stub |

## data (16)

| Connector | Protocols | AIA risk | Min trust | Maturity |
|---|---|---|---|---|
| postgresql | SQL | AIA-R1 | 50 | stub |
| mysql | SQL | AIA-R1 | 50 | stub |
| sqlserver | SQL | AIA-R1 | 50 | stub |
| oracle-db | SQL | AIA-R1 | 50 | stub |
| mongodb | Wire | AIA-R1 | 50 | stub |
| cassandra | CQL | AIA-R1 | 50 | stub |
| dynamodb | REST | AIA-R1 | 50 | stub |
| redis | RESP | AIA-R0 | 40 | stub |
| memcached | Memcache | AIA-R0 | 40 | stub |
| pgvector | SQL | AIA-R1 | 50 | stub |
| pinecone | REST | AIA-R1 | 50 | stub |
| weaviate | REST, GraphQL | AIA-R1 | 50 | stub |
| milvus | gRPC | AIA-R1 | 50 | stub |
| qdrant | REST, gRPC | AIA-R1 | 50 | stub |
| neo4j | Bolt | AIA-R1 | 50 | stub |
| elasticsearch | REST | AIA-R1 | 50 | stub |

## messaging (8)

| Connector | Protocols | AIA risk | Min trust | Maturity |
|---|---|---|---|---|
| kafka | Kafka | AIA-R1 | 50 | stub |
| nats | NATS | AIA-R0 | 40 | stub |
| rabbitmq | AMQP | AIA-R0 | 40 | stub |
| mqtt | MQTT | AIA-R0 | 40 | stub |
| amqp | AMQP | AIA-R0 | 40 | stub |
| pulsar | Pulsar | AIA-R0 | 40 | stub |
| aws-sqs | REST | AIA-R1 | 50 | stub |
| azure-servicebus | AMQP, REST | AIA-R1 | 50 | stub |

## industrial (8)

| Connector | Protocols | AIA risk | Min trust | Maturity |
|---|---|---|---|---|
| opcua | OPC-UA | AIA-R3 | 70 | stub |
| modbus | Modbus | AIA-R3 | 70 | stub |
| bacnet | BACnet | AIA-R3 | 70 | stub |
| scada | OPC-UA, Custom | AIA-R3 | 70 | stub |
| plc | Modbus, Custom | AIA-R3 | 70 | stub |
| sparkplug | MQTT-Sparkplug | AIA-R3 | 70 | stub |
| profinet | PROFINET | AIA-R3 | 70 | stub |
| ethernet-ip | EtherNet/IP | AIA-R3 | 70 | stub |

## cloud (10)

| Connector | Protocols | AIA risk | Min trust | Maturity |
|---|---|---|---|---|
| aws-s3 | REST | AIA-R1 | 50 | stub |
| aws-lambda | REST | AIA-R1 | 50 | stub |
| aws-eks | REST | AIA-R2 | 60 | stub |
| azure-blob | REST | AIA-R1 | 50 | stub |
| azure-aks | REST | AIA-R2 | 60 | stub |
| azure-functions | REST | AIA-R1 | 50 | stub |
| gcp-storage | REST | AIA-R1 | 50 | stub |
| gcp-gke | REST | AIA-R2 | 60 | stub |
| gcp-cloudrun | REST | AIA-R1 | 50 | stub |
| cloudflare | REST | AIA-R1 | 50 | stub |

## government (4)

| Connector | Protocols | AIA risk | Min trust | Maturity |
|---|---|---|---|---|
| gov-digital-identity | REST, OIDC | AIA-R3 | 70 | stub |
| gov-citizen-services | REST | AIA-R3 | 70 | stub |
| gov-notify | REST | AIA-R2 | 60 | stub |
| gov-pay | REST | AIA-R3 | 70 | stub |

## education (4)

| Connector | Protocols | AIA risk | Min trust | Maturity |
|---|---|---|---|---|
| moodle | REST | AIA-R2 | 60 | stub |
| canvas | REST, GraphQL | AIA-R2 | 60 | stub |
| blackboard | REST | AIA-R2 | 60 | stub |
| google-classroom | REST | AIA-R2 | 60 | stub |

## blockchain (7)

| Connector | Protocols | AIA risk | Min trust | Maturity |
|---|---|---|---|---|
| ethereum | JSON-RPC | AIA-R2 | 60 | specialized |
| polygon | JSON-RPC | AIA-R2 | 60 | stub |
| base | JSON-RPC | AIA-R2 | 60 | stub |
| avalanche | JSON-RPC | AIA-R2 | 60 | stub |
| bitcoin | JSON-RPC | AIA-R2 | 60 | stub |
| solana | JSON-RPC | AIA-R2 | 60 | stub |
| hyperledger-fabric | gRPC | AIA-R1 | 50 | stub |
