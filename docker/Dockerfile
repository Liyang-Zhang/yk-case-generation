FROM mambaorg/micromamba:1.5.8

# Copy environment spec and create env
COPY env/environment.yml /tmp/environment.yml
RUN micromamba create -y -f /tmp/environment.yml && \
    micromamba clean --all --yes

# System deps for DOCX->PDF rendering with correct CJK fonts
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-noto-cjk \
        fonts-wqy-zenhei \
        fonts-wqy-microhei \
        poppler-utils \
        unrar-free \
        p7zip-full && \
    fc-cache -fv && \
    rm -rf /var/lib/apt/lists/*

# Set env activation
ENV MAMBA_DEFAULT_ENV=yk-case-generation
ENV PATH=/opt/conda/envs/yk-case-generation/bin:$PATH
ENV LANG=zh_CN.UTF-8
ENV LC_ALL=zh_CN.UTF-8

WORKDIR /app
COPY . /app

# Install in editable mode
RUN pip install -e .

ENTRYPOINT ["ykcg"]
CMD ["--help"]
