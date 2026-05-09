FROM public.ecr.aws/lambda/python:3.12

WORKDIR /var/task

COPY pdf_parser/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY pdf_parser ./pdf_parser

CMD ["pdf_parser.index.lambda_handler"]
