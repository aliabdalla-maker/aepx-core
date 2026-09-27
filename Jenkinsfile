// AEP-X CI pipeline. Point a "Pipeline script from SCM" (or Multibranch
// Pipeline) job at this repo's GitHub remote to run it — see
// docs/Operational-Manual.html for the one-time Jenkins setup steps
// (docker-compose.jenkins.yml, opt-in, not started by default).
//
// Design note: this Jenkins runs with the HOST's docker.sock mounted
// (Docker-outside-of-Docker), not a nested Docker daemon. That means
// `docker build` / `docker compose build` work normally (a build context
// is streamed to the daemon, not bind-mounted), but a nested `docker run
// -v` or `docker compose up` with relative volume mounts would resolve
// against the wrong filesystem. So: lint/unit tests run natively in this
// image (see jenkins/Dockerfile for the python3 install), and the
// integration stage drives the v1 test environment over plain HTTP rather
// than assuming shared bind-mount paths.
pipeline {
    agent any
    options { timestamps(); disableConcurrentBuilds() }

    environment {
        COMPOSE_PROJECT_NAME = 'aepx-ci'
    }

    stages {
        stage('Lint + Unit Tests') {
            steps {
                script {
                    def components = [
                        'services/identity', 'services/trust', 'services/registry', 'services/memory',
                        'services/cache', 'services/gateway', 'services/discovery', 'services/workflow',
                        'services/safety', 'services/governance', 'services/knowledge', 'services/verification',
                        'services/cost-optimiser', 'services/ml-integration', 'services/brain',
                        'services/oracle-bridge', 'services/marketplace', 'services/billing',
                        'connector-bus', 'connectors/enterprise', 'connectors/productivity', 'connectors/devtools',
                        'connectors/aiplatform', 'connectors/data', 'connectors/messaging', 'connectors/industrial',
                        'connectors/cloud', 'connectors/government', 'connectors/education', 'connectors/blockchain', 'console',
                        'sdk/python', 'platform/conformance', 'platform/workbench', 'platform/aepx-console',
                    ]
                    // Keep this list and the pins below in step with
                    // .github/workflows/ci.yml (the source of truth).
                    def branches = [:]
                    for (c in components) {
                        def dir = c
                        // Absolute venv path — component dirs have inconsistent
                        // nesting depth (services/x vs console), which broke a
                        // relative "../../venv" traversal for the shallow ones.
                        def venv = "\$WORKSPACE/.venv-${dir.replace('/', '-')}"
                        branches[dir] = {
                            sh """
                                set -e
                                python3 -m venv "${venv}"
                                "${venv}/bin/pip" install -q --upgrade pip
                                "${venv}/bin/pip" install -q -r ${dir}/requirements.txt pytest httpx2 ruff==0.16.0
                                if [ "${dir}" = "services/cache" ] || [ "${dir}" = "services/discovery" ]; then
                                    "${venv}/bin/pip" install -q fakeredis==2.37.0
                                fi
                                # the SDK's own tests and both platform services import `aepx`
                                case "${dir}" in sdk/python|platform/*)
                                    "${venv}/bin/pip" install -q -e sdk/python ;;
                                esac
                                "${venv}/bin/ruff" check ${dir}
                                # python -m pytest (not bare pytest) puts the component
                                # dir on sys.path so `app.main` imports, as in ci.yml.
                                (cd ${dir} && "${venv}/bin/python" -m pytest tests -v)
                                rm -rf "${venv}"
                            """
                        }
                    }
                    parallel branches
                }
            }
        }

        stage('Contracts') {
            // RFC-0006/0008 Solidity integration on an in-memory EVM — mirrors
            // the `contracts` job in ci.yml. No Docker or anvil needed.
            steps {
                sh '''
                    set -e
                    python3 -m venv "$WORKSPACE/.venv-contracts"
                    "$WORKSPACE/.venv-contracts/bin/pip" install -q --upgrade pip
                    "$WORKSPACE/.venv-contracts/bin/pip" install -q -r tests/requirements.txt
                    "$WORKSPACE/.venv-contracts/bin/python" -m pytest tests/test_contracts.py -v
                    rm -rf "$WORKSPACE/.venv-contracts"
                '''
            }
        }

        stage('Build Images') {
            steps {
                // Build-only: context is streamed to the daemon, so this is
                // safe over the Docker-outside-of-Docker socket even though
                // a running-container volume mount would not be.
                sh 'docker compose build'
            }
        }

        stage('v1 Integration Smoke Test') {
            steps {
                sh 'bash tests/v1/run_smoke_test.sh'
            }
        }
    }

    post {
        always {
            // tests/v1/run_smoke_test.sh brings the v1 env up as project
            // `aepx-test`; tear down that project (its own EXIT trap normally
            // does this already — this is the backstop).
            sh 'docker compose -p aepx-test -f docker-compose.test.yml down -v --remove-orphans || true'
        }
        success {
            echo 'AEP-X: lint, unit tests, image build, and the v1 smoke test all passed.'
        }
        failure {
            echo 'AEP-X: pipeline failed — see the failing stage above for which component broke.'
        }
    }
}
