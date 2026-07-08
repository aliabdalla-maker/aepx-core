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
                        'connector-bus', 'connectors/enterprise', 'connectors/productivity', 'connectors/devtools',
                        'connectors/aiplatform', 'connectors/data', 'connectors/messaging', 'connectors/industrial',
                        'connectors/cloud', 'connectors/government', 'connectors/education', 'console',
                    ]
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
                                "${venv}/bin/pip" install -q -r ${dir}/requirements.txt pytest==8.2.0 ruff
                                if [ "${dir}" = "services/cache" ] || [ "${dir}" = "services/discovery" ]; then
                                    "${venv}/bin/pip" install -q fakeredis==2.23.2
                                fi
                                "${venv}/bin/ruff" check ${dir}
                                (cd ${dir} && "${venv}/bin/pytest" tests -v)
                                rm -rf "${venv}"
                            """
                        }
                    }
                    parallel branches
                }
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
            sh 'docker compose -p ${COMPOSE_PROJECT_NAME} -f docker-compose.test.yml down -v --remove-orphans || true'
        }
        success {
            echo 'AEP-X: lint, unit tests, image build, and the v1 smoke test all passed.'
        }
        failure {
            echo 'AEP-X: pipeline failed — see the failing stage above for which component broke.'
        }
    }
}
