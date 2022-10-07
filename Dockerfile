# syntax = docker/dockerfile:1

FROM golang:1.19-alpine AS build-base
WORKDIR /src
RUN apk add --no-cache file git
ENV GOMODCACHE /root/.cache/gocache

# Build daggerd linux binary
FROM build-base AS build-linux
RUN --mount=target=. --mount=target=/root/.cache,type=cache \
    CGO_ENABLED=0 GOOS=linux go build -o /bin/cloak -ldflags '-s -d -w' ./cmd/cloak

# Build dagger binary
FROM build-base AS build
RUN --mount=target=. --mount=target=/root/.cache,type=cache \
    CGO_ENABLED=0 go build -o /bin/cloak -ldflags '-s -d -w' ./cmd/cloak

# serve daggerd from alpine
FROM alpine AS daggerd
RUN apk add -U --no-cache runc git
COPY --from=docker:20.10.17-cli-alpine3.16 /usr/local/bin/docker /usr/local/bin/docker
COPY --from=build /bin/cloak /bin/cloak
RUN ln -s $(which cloak) /usr/bin/buildctl
ENTRYPOINT ["/bin/cloak", "serve"]

# serve dagger from alpine
FROM alpine:3.16
RUN apk add -U --no-cache ca-certificates
COPY --from=docker:20.10.17-cli-alpine3.16 /usr/local/bin/docker /usr/local/bin/docker
COPY --from=build /bin/cloak /bin/cloak
ENTRYPOINT ["/bin/cloak"]
