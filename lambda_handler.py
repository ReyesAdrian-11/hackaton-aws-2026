"""Optional AWS Lambda adapter for short HTTP requests.

The main simulation remains on EC2. This adapter is intended only for short
read-only or stateless API Gateway requests; it does not replace uvicorn or
the long-running SimulationService.
"""

from mangum import Mangum

from main import app


handler = Mangum(app)
